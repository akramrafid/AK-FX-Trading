//+------------------------------------------------------------------+
//|                                             DWX_AutoTrader.mq4   |
//|                             AkStack Automated MT4 Trading Bridge |
//|                               https://github.com/akramrafid      |
//+------------------------------------------------------------------+
#property copyright "AkStack Trading Systems"
#property link      "https://github.com/akramrafid"
#property version   "1.00"
#property strict

//--- Input parameters
input int      MaxSlippagePips   = 3;                 // Maximum allowed slippage in pips
input int      PollTimerMillis   = 200;               // Command polling timer in milliseconds
input int      ExportBarsCount   = 50;                // Number of historical closed bars to export
input string   CommandsFilename  = "DWX_Commands.txt"; // Command file name
input string   ReportsFilename   = "DWX_Reports.txt";  // Execution report file name

//--- Global state
static datetime g_lastBarTime = 0;
static string   g_symbolBarsFile = "";

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   g_lastBarTime = Time[0];
   g_symbolBarsFile = "DWX_Bars_" + Symbol() + "_M" + IntegerToString(Period()) + ".txt";

   Print("[DWX_AutoTrader] Initializing bridge on ", Symbol(), " M", Period());
   Print("[DWX_AutoTrader] Bars export file: ", g_symbolBarsFile);
   Print("[DWX_AutoTrader] Commands file:    ", CommandsFilename);
   Print("[DWX_AutoTrader] Reports file:     ", ReportsFilename);

   // Export initial historical bars
   ExportRecentBars(ExportBarsCount);

   // Start high-resolution timer for command polling
   EventSetMillisecondTimer(PollTimerMillis);

   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("[DWX_AutoTrader] Shutdown. Reason code: ", reason);
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   // Closed-bar detection: check if a new bar has just opened
   datetime currentBarTime = Time[0];
   if (currentBarTime != g_lastBarTime)
   {
      g_lastBarTime = currentBarTime;
      // Bar 1 is now fully closed and sealed
      ExportRecentBars(ExportBarsCount);
      Print("[DWX_AutoTrader] New bar closed at ", TimeToStr(Time[1], TIME_DATE|TIME_SECONDS));
   }
}

//+------------------------------------------------------------------+
//| Timer event function for command processing                      |
//+------------------------------------------------------------------+
void OnTimer()
{
   ProcessPendingCommands();
}

//+------------------------------------------------------------------+
//| Export recent closed bars to CSV file                            |
//+------------------------------------------------------------------+
void ExportRecentBars(int count)
{
   int fileHandle = FileOpen(g_symbolBarsFile, FILE_WRITE|FILE_TXT|FILE_SHARE_READ|FILE_SHARE_WRITE);
   if (fileHandle == INVALID_HANDLE)
   {
      Print("[DWX_AutoTrader] Error opening bars file for write: ", GetLastError());
      return;
   }

   // Write CSV header
   FileWriteString(fileHandle, "timestamp,open,high,low,close,volume\n");

   int limit = MathMin(count, Bars - 1);
   // Write from oldest closed bar to newest closed bar (bar 1)
   for (int i = limit; i >= 1; i--)
   {
      string timeStr = TimeToStr(Time[i], TIME_DATE|TIME_SECONDS);
      // Format: YYYY.MM.DD HH:MM:SS -> convert dot to dash for ISO
      StringReplace(timeStr, ".", "-");

      string line = StringFormat("%s,%.5f,%.5f,%.5f,%.5f,%d\n",
                                 timeStr,
                                 Open[i],
                                 High[i],
                                 Low[i],
                                 Close[i],
                                 (long)Volume[i]);
      FileWriteString(fileHandle, line);
   }

   FileClose(fileHandle);
}

//+------------------------------------------------------------------+
//| Process and execute commands written by Python                   |
//+------------------------------------------------------------------+
void ProcessPendingCommands()
{
   if (!FileIsExist(CommandsFilename))
      return;

   int fileHandle = FileOpen(CommandsFilename, FILE_READ|FILE_TXT|FILE_SHARE_READ|FILE_SHARE_WRITE);
   if (fileHandle == INVALID_HANDLE)
      return;

   string lines[];
   int count = 0;

   while (!FileIsEnding(fileHandle))
   {
      string line = FileReadString(fileHandle);
      StringTrimLeft(line);
      StringTrimRight(line);
      if (StringLen(line) > 5)
      {
         ArrayResize(lines, count + 1);
         lines[count] = line;
         count++;
      }
   }
   FileClose(fileHandle);

   if (count == 0)
      return;

   // Truncate commands file immediately so commands are not re-executed
   int clearHandle = FileOpen(CommandsFilename, FILE_WRITE|FILE_TXT|FILE_SHARE_READ|FILE_SHARE_WRITE);
   if (clearHandle != INVALID_HANDLE)
   {
      FileWriteString(clearHandle, "");
      FileClose(clearHandle);
   }

   // Execute each command
   for (int i = 0; i < count; i++)
   {
      ExecuteSingleCommand(lines[i]);
   }
}

//+------------------------------------------------------------------+
//| Execute a single JSON command string                             |
//+------------------------------------------------------------------+
void ExecuteSingleCommand(string jsonStr)
{
   string action  = GetJsonString(jsonStr, "action");
   string cmdId   = GetJsonString(jsonStr, "command_id");
   string sym     = GetJsonString(jsonStr, "symbol");
   if (StringLen(sym) == 0) sym = Symbol();

   Print("[DWX_AutoTrader] Processing command: ", action, " ID: ", cmdId);

   if (action == "OPEN")
   {
      string typeStr = GetJsonString(jsonStr, "type");
      double lots    = GetJsonDouble(jsonStr, "lots");
      double sl      = GetJsonDouble(jsonStr, "sl");
      double tp      = GetJsonDouble(jsonStr, "tp");
      int    magic   = GetJsonInt(jsonStr, "magic");
      string comment = GetJsonString(jsonStr, "comment");
      if (StringLen(comment) == 0) comment = "akstack_auto";

      int cmdType = (typeStr == "BUY") ? OP_BUY : OP_SELL;
      double openPrice = (cmdType == OP_BUY) ? MarketInfo(sym, MODE_ASK) : MarketInfo(sym, MODE_BID);
      int slippagePoints = MaxSlippagePips * (int)MarketInfo(sym, MODE_POINT);

      RefreshRates();
      int ticket = OrderSend(sym, cmdType, lots, openPrice, slippagePoints, sl, tp, comment, magic, 0, (cmdType == OP_BUY ? clrGreen : clrRed));

      if (ticket > 0)
      {
         Print("[DWX_AutoTrader] Order FILLED! Ticket: ", ticket, " Magic: ", magic, " Price: ", openPrice);
         WriteReport(ticket, magic, sym, typeStr, lots, openPrice, sl, tp, "FILLED", 0, "Order opened successfully");
      }
      else
      {
         int err = GetLastError();
         Print("[DWX_AutoTrader] Order REJECTED! Error: ", err);
         WriteReport(0, magic, sym, typeStr, lots, 0.0, sl, tp, "ERROR", err, "OrderSend failed");
      }
   }
   else if (action == "CLOSE")
   {
      int ticket = GetJsonInt(jsonStr, "ticket");
      double closeLots = GetJsonDouble(jsonStr, "lots");

      if (OrderSelect(ticket, SELECT_BY_TICKET, MODE_TRADES))
      {
         double volume = (closeLots > 0.0) ? closeLots : OrderLots();
         double closePrice = (OrderType() == OP_BUY) ? MarketInfo(OrderSymbol(), MODE_BID) : MarketInfo(OrderSymbol(), MODE_ASK);
         int slippage = MaxSlippagePips * (int)MarketInfo(OrderSymbol(), MODE_POINT);

         if (OrderClose(ticket, volume, closePrice, slippage, clrOrange))
         {
            Print("[DWX_AutoTrader] Order CLOSED: Ticket ", ticket);
            WriteReport(ticket, OrderMagicNumber(), OrderSymbol(), (OrderType() == OP_BUY ? "BUY" : "SELL"), volume, closePrice, OrderStopLoss(), OrderTakeProfit(), "CLOSED", 0, "Order closed successfully");
         }
         else
         {
            int err = GetLastError();
            Print("[DWX_AutoTrader] OrderClose FAILED: ", err);
            WriteReport(ticket, OrderMagicNumber(), OrderSymbol(), (OrderType() == OP_BUY ? "BUY" : "SELL"), volume, closePrice, 0, 0, "ERROR", err, "OrderClose failed");
         }
      }
   }
   else if (action == "MODIFY")
   {
      int ticket = GetJsonInt(jsonStr, "ticket");
      double newSL = GetJsonDouble(jsonStr, "sl");
      double newTP = GetJsonDouble(jsonStr, "tp");

      if (OrderSelect(ticket, SELECT_BY_TICKET, MODE_TRADES))
      {
         if (OrderModify(ticket, OrderOpenPrice(), newSL, newTP, 0, clrBlue))
         {
            Print("[DWX_AutoTrader] Order MODIFIED: Ticket ", ticket);
            WriteReport(ticket, OrderMagicNumber(), OrderSymbol(), (OrderType() == OP_BUY ? "BUY" : "SELL"), OrderLots(), OrderOpenPrice(), newSL, newTP, "MODIFIED", 0, "Order modified successfully");
         }
         else
         {
            int err = GetLastError();
            Print("[DWX_AutoTrader] OrderModify FAILED: ", err);
            WriteReport(ticket, OrderMagicNumber(), OrderSymbol(), (OrderType() == OP_BUY ? "BUY" : "SELL"), OrderLots(), OrderOpenPrice(), newSL, newTP, "ERROR", err, "OrderModify failed");
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Write execution report JSON line to DWX_Reports.txt              |
//+------------------------------------------------------------------+
void WriteReport(int ticket, int magic, string sym, string orderType, double lots, double openPrice, double sl, double tp, string status, int errCode, string msg)
{
   int fileHandle = FileOpen(ReportsFilename, FILE_READ|FILE_WRITE|FILE_TXT|FILE_SHARE_READ|FILE_SHARE_WRITE);
   if (fileHandle == INVALID_HANDLE)
   {
      Print("[DWX_AutoTrader] Error opening reports file: ", GetLastError());
      return;
   }

   FileSeek(fileHandle, 0, SEEK_END);

   string timeStr = TimeToStr(TimeCurrent(), TIME_DATE|TIME_SECONDS);
   StringReplace(timeStr, ".", "-");

   string json = StringFormat("{\"ticket\":%d,\"magic\":%d,\"symbol\":\"%s\",\"type\":\"%s\",\"lots\":%.2f,\"open_price\":%.5f,\"sl\":%.5f,\"tp\":%.5f,\"status\":\"%s\",\"error_code\":%d,\"message\":\"%s\",\"timestamp\":\"%s\"}\n",
                              ticket, magic, sym, orderType, lots, openPrice, sl, tp, status, errCode, msg, timeStr);

   FileWriteString(fileHandle, json);
   FileClose(fileHandle);
}

//+------------------------------------------------------------------+
//| Helper JSON extraction utilities                                 |
//+------------------------------------------------------------------+
string GetJsonString(string json, string key)
{
   string searchKey = "\"" + key + "\":";
   int pos = StringFind(json, searchKey);
   if (pos < 0) return "";

   int start = pos + StringLen(searchKey);
   // Skip whitespace
   while (start < StringLen(json) && (StringSubstr(json, start, 1) == " " || StringSubstr(json, start, 1) == "\""))
      start++;

   int end = start;
   while (end < StringLen(json) && StringSubstr(json, end, 1) != "\"" && StringSubstr(json, end, 1) != "," && StringSubstr(json, end, 1) != "}")
      end++;

   return StringSubstr(json, start, end - start);
}

double GetJsonDouble(string json, string key)
{
   string val = GetJsonString(json, key);
   return StringToDouble(val);
}

int GetJsonInt(string json, string key)
{
   string val = GetJsonString(json, key);
   return (int)StringToInteger(val);
}
//+------------------------------------------------------------------+

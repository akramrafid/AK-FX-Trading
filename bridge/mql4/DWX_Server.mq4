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
input string   AccountFilename   = "DWX_Account.txt";  // Account info file name

//--- Global state
static datetime g_lastBarTime = 0;
static string   g_symbolBarsFile = "";
static ulong    g_lastAccountExportMs = 0;

// Forward declaration
void ExportAccountInfo();
void EnsureChartIsOpen(string sym, int tf);

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
   Print("[DWX_AutoTrader] Account file:     ", AccountFilename);

   // Ensure required charts are active in terminal for multi-timeframe streaming
   EnsureChartIsOpen(Symbol(), PERIOD_M1);
   EnsureChartIsOpen(Symbol(), PERIOD_M15);

   // Export initial historical bars and account state
   ExportRecentBars(ExportBarsCount);
   ExportAccountInfo();

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

   ExportAccountInfo();
}

//+------------------------------------------------------------------+
//| Timer event function for command processing                      |
//+------------------------------------------------------------------+
void OnTimer()
{
   ProcessPendingCommands();

   // Export account state and multi-timeframe closed bars every 1 second
   ulong now = GetTickCount();
   if (now - g_lastAccountExportMs >= 1000)
   {
      g_lastAccountExportMs = now;
      ExportAccountInfo();
      ExportRecentBars(ExportBarsCount);
   }
}

void EnsureChartIsOpen(string sym, int tf)
{
   long chartId = ChartFirst();
   while (chartId >= 0)
   {
      if (ChartSymbol(chartId) == sym && ChartPeriod(chartId) == tf)
         return; // Already open
      chartId = ChartNext(chartId);
   }
   long newChart = ChartOpen(sym, (ENUM_TIMEFRAMES)tf);
   if (newChart > 0)
      Print("[DWX_AutoTrader] Opened chart for ", sym, " M", tf, " ChartID=", newChart);
   else
      Print("[DWX_AutoTrader] Note: ChartOpen for ", sym, " M", tf, " returned ", newChart, " err=", GetLastError());
}

//+------------------------------------------------------------------+
//| Export recent closed bars to CSV file for a given symbol         |
//+------------------------------------------------------------------+
void ExportBarsForSymbol(string sym, int tf, int count)
{
   int totalBars = iBars(sym, tf);
   if (totalBars <= 1)
   {
      // Ensure chart is active in terminal to download and stream data
      EnsureChartIsOpen(sym, tf);
      iClose(sym, tf, 0);
      return;
   }

   string filename = "DWX_Bars_" + sym + "_M" + IntegerToString(tf) + ".txt";
   int fileHandle = FileOpen(filename, FILE_WRITE|FILE_TXT|FILE_SHARE_READ|FILE_SHARE_WRITE);
   if (fileHandle == INVALID_HANDLE)
   {
      Print("[DWX_AutoTrader] Error opening bars file for ", sym, ": ", GetLastError());
      return;
   }

   FileWriteString(fileHandle, "timestamp,open,high,low,close,volume\n");

   int limit = MathMin(count, totalBars - 1);
   for (int i = limit; i >= 1; i--)
   {
      string timeStr = TimeToStr(iTime(sym, tf, i), TIME_DATE|TIME_SECONDS);
      StringReplace(timeStr, ".", "-");

      string line = StringFormat("%s,%.5f,%.5f,%.5f,%.5f,%d\n",
                                 timeStr,
                                 iOpen(sym, tf, i),
                                 iHigh(sym, tf, i),
                                 iLow(sym, tf, i),
                                 iClose(sym, tf, i),
                                 (long)iVolume(sym, tf, i));
      FileWriteString(fileHandle, line);
   }

   FileClose(fileHandle);
}

//+------------------------------------------------------------------+
//| Export recent closed bars for configured symbols                 |
//+------------------------------------------------------------------+
void ExportRecentBars(int count)
{
   string sym1 = Symbol();
   string sym2 = "USDCAD";
   if (StringFind(sym1, "m") >= 0) sym2 = "USDCADm";
   else if (StringFind(sym1, "c") >= 0) sym2 = "USDCADc";

   int tfs[3] = {PERIOD_M1, PERIOD_M5, PERIOD_M15};
   for (int i = 0; i < 3; i++)
   {
      ExportBarsForSymbol(sym1, tfs[i], count);
      ExportBarsForSymbol(sym2, tfs[i], count);
   }
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
   
   // Normalize symbol: if empty or matching current chart symbol case-insensitively, use exact Symbol()
   if (StringLen(sym) == 0 || StringCompare(sym, Symbol(), false) == 0)
   {
      sym = Symbol();
   }

   Print("[DWX_AutoTrader] Processing command: ", action, " ID: ", cmdId, " TargetSymbol: ", sym, " (Chart: ", Symbol(), ")");

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
      
      RefreshRates();
      double openPrice = 0.0;
      if (sym == Symbol())
      {
         openPrice = (cmdType == OP_BUY) ? Ask : Bid;
      }
      else
      {
         openPrice = (cmdType == OP_BUY) ? MarketInfo(sym, MODE_ASK) : MarketInfo(sym, MODE_BID);
      }

      int pFactor = (Digits == 3 || Digits == 5) ? 10 : 1;
      int slippagePoints = MaxSlippagePips * pFactor;

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
         string ordSym = OrderSymbol();
         double volume = (closeLots > 0.0) ? closeLots : OrderLots();
         
         RefreshRates();
         double closePrice = 0.0;
         if (ordSym == Symbol())
         {
            closePrice = (OrderType() == OP_BUY) ? Bid : Ask;
         }
         else
         {
            closePrice = (OrderType() == OP_BUY) ? MarketInfo(ordSym, MODE_BID) : MarketInfo(ordSym, MODE_ASK);
         }
         
         int pFactor = (Digits == 3 || Digits == 5) ? 10 : 1;
         int slippage = MaxSlippagePips * pFactor;

         if (OrderClose(ticket, volume, closePrice, slippage, clrOrange))
         {
            Print("[DWX_AutoTrader] Order CLOSED: Ticket ", ticket);
            WriteReport(ticket, OrderMagicNumber(), ordSym, (OrderType() == OP_BUY ? "BUY" : "SELL"), volume, closePrice, OrderStopLoss(), OrderTakeProfit(), "CLOSED", 0, "Order closed successfully");
         }
         else
         {
            int err = GetLastError();
            Print("[DWX_AutoTrader] OrderClose FAILED: ", err);
            WriteReport(ticket, OrderMagicNumber(), ordSym, (OrderType() == OP_BUY ? "BUY" : "SELL"), volume, closePrice, 0, 0, "ERROR", err, "OrderClose failed");
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
   ExportAccountInfo();
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
//| Export MT4 account info and active open orders                   |
//+------------------------------------------------------------------+
void ExportAccountInfo()
{
   int fileHandle = FileOpen(AccountFilename, FILE_WRITE|FILE_TXT|FILE_SHARE_READ|FILE_SHARE_WRITE);
   if (fileHandle == INVALID_HANDLE)
   {
      return;
   }

   RefreshRates();
   double balance     = AccountBalance();
   double equity      = AccountEquity();
   double margin      = AccountMargin();
   double freeMargin  = AccountFreeMargin();
   double profit      = AccountProfit();
   int    leverage    = AccountLeverage();
   string company     = AccountCompany();
   int    accNum      = AccountNumber();
   string currency    = AccountCurrency();
   string accName     = AccountName();
   
   double bid = Bid;
   double ask = Ask;
   int pFactor = (Digits == 3 || Digits == 5) ? 10 : 1;
   double spreadPips = (ask - bid) / (Point * pFactor);

   // Build open orders array
   string ordersJson = "[";
   int total = OrdersTotal();
   bool first = true;
   for (int i = 0; i < total; i++)
   {
      if (OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
      {
         if (!first) ordersJson += ",";
         first = false;
         
         string oType = (OrderType() == OP_BUY) ? "BUY" : (OrderType() == OP_SELL ? "SELL" : "PENDING");
         string openTimeStr = TimeToStr(OrderOpenTime(), TIME_DATE|TIME_SECONDS);
         StringReplace(openTimeStr, ".", "-");

         double curPrice = (OrderType() == OP_BUY) ? Bid : Ask;
         if (OrderSymbol() != Symbol())
         {
            curPrice = (OrderType() == OP_BUY) ? MarketInfo(OrderSymbol(), MODE_BID) : MarketInfo(OrderSymbol(), MODE_ASK);
         }

         string ordStr = StringFormat("{\"ticket\":%d,\"symbol\":\"%s\",\"type\":\"%s\",\"lots\":%.2f,\"open_price\":%.5f,",
                                      OrderTicket(), OrderSymbol(), oType, OrderLots(), OrderOpenPrice());
         ordStr += StringFormat("\"current_price\":%.5f,\"sl\":%.5f,\"tp\":%.5f,\"profit\":%.2f,\"magic\":%d,",
                                curPrice, OrderStopLoss(), OrderTakeProfit(), OrderProfit(), OrderMagicNumber());
         ordStr += StringFormat("\"comment\":\"%s\",\"open_time\":\"%s\"}",
                                OrderComment(), openTimeStr);
         ordersJson += ordStr;
      }
   }
   ordersJson += "]";

   string timeStr = TimeToStr(TimeCurrent(), TIME_DATE|TIME_SECONDS);
   StringReplace(timeStr, ".", "-");

   string eurusdSym = "EURUSD";
   if (StringFind(Symbol(), "m") >= 0) eurusdSym = "EURUSDm";
   string usdcadSym = "USDCAD";
   if (StringFind(Symbol(), "m") >= 0) usdcadSym = "USDCADm";

   double eBid = (Symbol() == eurusdSym) ? Bid : MarketInfo(eurusdSym, MODE_BID);
   double eAsk = (Symbol() == eurusdSym) ? Ask : MarketInfo(eurusdSym, MODE_ASK);
   double ePt = (Symbol() == eurusdSym) ? Point : MarketInfo(eurusdSym, MODE_POINT);
   double eSpread = (ePt > 0) ? (eAsk - eBid) / (ePt * 10.0) : 0.8;

   double uBid = (Symbol() == usdcadSym) ? Bid : MarketInfo(usdcadSym, MODE_BID);
   double uAsk = (Symbol() == usdcadSym) ? Ask : MarketInfo(usdcadSym, MODE_ASK);
   double uPt = (Symbol() == usdcadSym) ? Point : MarketInfo(usdcadSym, MODE_POINT);
   double uSpread = (uPt > 0) ? (uAsk - uBid) / (uPt * 10.0) : 1.4;

   string pairsJson = "{\"EURUSDm\":{\"bid\":" + DoubleToStr(eBid, 5) + ",\"ask\":" + DoubleToStr(eAsk, 5) + ",\"spread_pips\":" + DoubleToStr(eSpread, 2) + "}," +
                      "\"USDCADm\":{\"bid\":" + DoubleToStr(uBid, 5) + ",\"ask\":" + DoubleToStr(uAsk, 5) + ",\"spread_pips\":" + DoubleToStr(uSpread, 2) + "}}";

   string outJson = "{";
   outJson += StringFormat("\"account_number\":%d,\"company\":\"%s\",\"account_name\":\"%s\",\"currency\":\"%s\",",
                          accNum, company, accName, currency);
   outJson += StringFormat("\"balance\":%.2f,\"equity\":%.2f,\"margin\":%.2f,\"free_margin\":%.2f,\"profit\":%.2f,\"leverage\":%d,",
                          balance, equity, margin, freeMargin, profit, leverage);
   outJson += StringFormat("\"symbol\":\"%s\",\"bid\":%.5f,\"ask\":%.5f,\"spread_pips\":%.2f,\"digits\":%d,",
                          Symbol(), bid, ask, spreadPips, Digits);
   outJson += StringFormat("\"pairs\":%s,\"timestamp\":\"%s\",\"open_orders_count\":%d,\"orders\":%s}\n",
                          pairsJson, timeStr, total, ordersJson);

   FileWriteString(fileHandle, outJson);
   FileClose(fileHandle);
}
//+------------------------------------------------------------------+


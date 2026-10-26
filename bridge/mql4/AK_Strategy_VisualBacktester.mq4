//+------------------------------------------------------------------+
//|                                AK_Strategy_VisualBacktester.mq4   |
//|               AK Pure MQL4 Visual Backtest & Live Chart Strategy  |
//|                                  https://github.com/akramrafid   |
//+------------------------------------------------------------------+
#property copyright "AkStack Trading Systems"
#property link      "https://github.com/akramrafid"
#property version   "1.00"
#property strict

//--- Inputs
input double RewardRiskRatio     = 10.0;     // Reward-to-Risk Ratio (e.g. 10.0 for 1:10)
input double RiskPercent         = 1.0;      // Risk % per trade based on Account Balance
input double BreakevenR          = 2.0;      // Move SL to Breakeven at +X.X R (0 to disable)
input int    MaxOpenTrades       = 5;        // Maximum concurrent open positions
input int    SessionStartHour    = 7;        // Session Start Hour (UTC)
input int    SessionEndHour      = 18;       // Session End Hour (UTC, 18 = 12 AM Dhaka)
input bool   EnableM5Sweep       = true;     // Check M5 Liquidity Sweeps
input bool   EnableM15Sweep      = true;     // Check M15 Liquidity Sweeps
input int    MagicNumber         = 106123;   // Strategy Order Magic Number
input int    SlippagePips        = 3;        // Allowed Slippage in pips

//--- Internal State
static datetime g_lastM1BarTime = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   g_lastM1BarTime = iTime(Symbol(), PERIOD_M1, 0);
   Print("[AK_VisualBacktester] Initialized on ", Symbol(), ". Strategy: 1:", DoubleToString(RewardRiskRatio, 1), " RR. Risk: ", DoubleToString(RiskPercent, 1), "%");
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   Print("[AK_VisualBacktester] Deinitialized. Reason: ", reason);
}

//+------------------------------------------------------------------+
//| Check if current candle is within trading session (UTC)          |
//+------------------------------------------------------------------+
bool IsInSession(datetime barTime)
{
   MqlDateTime dt;
   TimeToStruct(barTime, dt);
   // Note: MT4 broker server time is typically GMT+2/GMT+3. Assuming UTC input:
   if (dt.hour >= SessionStartHour && dt.hour < SessionEndHour)
      return true;
   return false;
}

//+------------------------------------------------------------------+
//| Count active positions for this magic number                     |
//+------------------------------------------------------------------+
int CountOpenPositions()
{
   int count = 0;
   for (int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if (OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
      {
         if (OrderSymbol() == Symbol() && OrderMagicNumber() == MagicNumber)
         {
            if (OrderType() == OP_BUY || OrderType() == OP_SELL)
               count++;
         }
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| Calculate Lot Size based on Risk % and Stop Loss distance        |
//+------------------------------------------------------------------+
double CalculateLotSize(double slDistance)
{
   if (slDistance <= 0.0) return 0.01;
   
   double riskCurrency = AccountBalance() * (RiskPercent / 100.0);
   double tickValue = MarketInfo(Symbol(), MODE_TICKVALUE);
   double tickSize  = MarketInfo(Symbol(), MODE_TICKSIZE);
   double pointVal  = MarketInfo(Symbol(), MODE_POINT);
   
   if (tickSize == 0.0 || tickValue == 0.0) return 0.01;
   
   double ticksAtRisk = slDistance / tickSize;
   double lotSize = riskCurrency / (ticksAtRisk * tickValue);
   
   double minLot = MarketInfo(Symbol(), MODE_MINLOT);
   double maxLot = MarketInfo(Symbol(), MODE_MAXLOT);
   double lotStep = MarketInfo(Symbol(), MODE_LOTSTEP);
   
   lotSize = MathFloor(lotSize / lotStep) * lotStep;
   if (lotSize < minLot) lotSize = minLot;
   if (lotSize > maxLot) lotSize = maxLot;
   
   return lotSize;
}

//+------------------------------------------------------------------+
//| Manage Open Positions (Breakeven adjustment at +2.0R)            |
//+------------------------------------------------------------------+
void ManageOpenPositions()
{
   if (BreakevenR <= 0.0) return;
   
   for (int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if (OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
      {
         if (OrderSymbol() == Symbol() && OrderMagicNumber() == MagicNumber)
         {
            double openPrice = OrderOpenPrice();
            double currentSL = OrderStopLoss();
            double initialRisk = MathAbs(openPrice - currentSL);
            if (initialRisk <= 0.00001) continue;
            
            if (OrderType() == OP_BUY)
            {
               // If SL is already at or above entry, it's already moved to BE
               if (currentSL >= openPrice) continue;
               
               double beTrigger = openPrice + (BreakevenR * initialRisk);
               if (Bid >= beTrigger)
               {
                  bool mod = OrderModify(OrderTicket(), openPrice, openPrice, OrderTakeProfit(), 0, clrBlue);
                  if (mod)
                     Print("[AK_VisualBacktester] Moved BUY Ticket #", OrderTicket(), " SL to Breakeven @ ", openPrice);
               }
            }
            else if (OrderType() == OP_SELL)
            {
               // If SL is already at or below entry, it's already moved to BE
               if (currentSL <= openPrice && currentSL > 0) continue;
               
               double beTrigger = openPrice - (BreakevenR * initialRisk);
               if (Ask <= beTrigger)
               {
                  bool mod = OrderModify(OrderTicket(), openPrice, openPrice, OrderTakeProfit(), 0, clrBlue);
                  if (mod)
                     Print("[AK_VisualBacktester] Moved SELL Ticket #", OrderTicket(), " SL to Breakeven @ ", openPrice);
               }
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Check for HTF Sweep Rejection                                    |
//+------------------------------------------------------------------+
bool CheckHTFSweep(int tf, int type, double &sweptLevel)
{
   // type: 0 = BUY (Sweep of Low), 1 = SELL (Sweep of High)
   // We look back over the last 3 closed HTF bars for a valid sweep
   for (int shift = 1; shift <= 3; shift++)
   {
      double o0 = iOpen(Symbol(), tf, shift);
      double c0 = iClose(Symbol(), tf, shift);
      double h0 = iHigh(Symbol(), tf, shift);
      double l0 = iLow(Symbol(), tf, shift);
      
      double o_prev = iOpen(Symbol(), tf, shift + 1);
      double c_prev = iClose(Symbol(), tf, shift + 1);
      double h_prev = iHigh(Symbol(), tf, shift + 1);
      double l_prev = iLow(Symbol(), tf, shift + 1);
      
      if (type == 0) // BUY sweep of prior low
      {
         // Prior bar was bearish (red), current swept its low and closed back inside
         if (c_prev < o_prev && l0 < l_prev && c0 > l_prev)
         {
            sweptLevel = l_prev;
            return true;
         }
         // Or intrabar sweep of active bar 0
         if (iLow(Symbol(), tf, 0) < l0 && iClose(Symbol(), tf, 0) > l0)
         {
            sweptLevel = l0;
            return true;
         }
      }
      else if (type == 1) // SELL sweep of prior high
      {
         // Prior bar was bullish (green), current swept its high and closed back inside
         if (c_prev > o_prev && h0 > h_prev && c0 < h_prev)
         {
            sweptLevel = h_prev;
            return true;
         }
         // Or intrabar sweep of active bar 0
         if (iHigh(Symbol(), tf, 0) > h0 && iClose(Symbol(), tf, 0) < h0)
         {
            sweptLevel = h0;
            return true;
         }
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//| Check for M1 3-Candle Directional Confirmation                   |
//+------------------------------------------------------------------+
bool CheckM1Confirmation(int type, double &c1Extreme)
{
   // type: 0 = BUY, 1 = SELL
   // Bar 3 = C1, Bar 2 = C2, Bar 1 = C3 (all completed M1 candles)
   double o1 = iOpen(Symbol(), PERIOD_M1, 3);
   double c1 = iClose(Symbol(), PERIOD_M1, 3);
   double h1 = iHigh(Symbol(), PERIOD_M1, 3);
   double l1 = iLow(Symbol(), PERIOD_M1, 3);
   
   double o2 = iOpen(Symbol(), PERIOD_M1, 2);
   double c2 = iClose(Symbol(), PERIOD_M1, 2);
   
   double o3 = iOpen(Symbol(), PERIOD_M1, 1);
   double c3 = iClose(Symbol(), PERIOD_M1, 1);
   
   if (type == 0) // BUY: 3 consecutive bullish closes
   {
      if (c1 > o1 && c2 > o2 && c3 > o3)
      {
         c1Extreme = l1; // Stop loss is C1 Low
         return true;
      }
   }
   else if (type == 1) // SELL: 3 consecutive bearish closes
   {
      if (c1 < o1 && c2 < o2 && c3 < o3)
      {
         c1Extreme = h1; // Stop loss is C1 High
         return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//| Main OnTick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   // 1. Manage active trades (Breakeven) on every tick
   ManageOpenPositions();
   
   // 2. Check for newly completed M1 bar
   datetime currentM1BarTime = iTime(Symbol(), PERIOD_M1, 0);
   if (currentM1BarTime == g_lastM1BarTime)
      return; // Wait until M1 bar completes
      
   g_lastM1BarTime = currentM1BarTime;
   
   // 3. Risk filter checks
   if (CountOpenPositions() >= MaxOpenTrades)
      return;
      
   if (!IsInSession(currentM1BarTime))
      return;
      
   // 4. Evaluate BUY setup
   double sweptLevelBuy = 0.0;
   bool hasBuySweep = (EnableM5Sweep && CheckHTFSweep(PERIOD_M5, 0, sweptLevelBuy)) ||
                      (EnableM15Sweep && CheckHTFSweep(PERIOD_M15, 0, sweptLevelBuy));
                      
   if (hasBuySweep)
   {
      double c1Low = 0.0;
      if (CheckM1Confirmation(0, c1Low))
      {
         double entry = Ask;
         double sl = c1Low;
         double riskDist = entry - sl;
         
         if (riskDist > 0.00010) // Minimum 1 pip risk distance
         {
            double tp = entry + (RewardRiskRatio * riskDist);
            double lots = CalculateLotSize(riskDist);
            
            int ticket = OrderSend(Symbol(), OP_BUY, lots, entry, SlippagePips, sl, tp, "AK Strict 1:10", MagicNumber, 0, clrGreen);
            if (ticket > 0)
            {
               Print("[AK_VisualBacktester] Executed BUY Ticket #", ticket, " @ ", entry, " SL: ", sl, " TP: ", tp, " Lots: ", lots);
               return;
            }
         }
      }
   }
   
   // 5. Evaluate SELL setup
   double sweptLevelSell = 0.0;
   bool hasSellSweep = (EnableM5Sweep && CheckHTFSweep(PERIOD_M5, 1, sweptLevelSell)) ||
                       (EnableM15Sweep && CheckHTFSweep(PERIOD_M15, 1, sweptLevelSell));
                       
   if (hasSellSweep)
   {
      double c1High = 0.0;
      if (CheckM1Confirmation(1, c1High))
      {
         double entry = Bid;
         double sl = c1High;
         double riskDist = sl - entry;
         
         if (riskDist > 0.00010) // Minimum 1 pip risk distance
         {
            double tp = entry - (RewardRiskRatio * riskDist);
            double lots = CalculateLotSize(riskDist);
            
            int ticket = OrderSend(Symbol(), OP_SELL, lots, entry, SlippagePips, sl, tp, "AK Strict 1:10", MagicNumber, 0, clrRed);
            if (ticket > 0)
            {
               Print("[AK_VisualBacktester] Executed SELL Ticket #", ticket, " @ ", entry, " SL: ", sl, " TP: ", tp, " Lots: ", lots);
               return;
            }
         }
      }
   }
}
//+------------------------------------------------------------------+

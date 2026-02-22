import os
# Add after existing bot modes
# Bot Modes
BACK = "Backtest"
SIM = "Simulation"  # Paper trading
LIVE = "Live"
OPTI = "Optimizer"

# Add new enums
PAPER = "Paper"  # Alias for SIM
BACKTEST = "Backtest"

# Backtest status
BACKTEST_PENDING = "Pending"
BACKTEST_RUNNING = "Running"
BACKTEST_COMPLETED = "Completed"
BACKTEST_FAILED = "Failed"

# Trade Types
TRADE_TYPE_SCALPING = "Scalping"
TRADE_TYPE_NORMAL = "Normal"
TRADE_TYPE_EXPIRY = "Expiry"

# Trend Indicators
BULLISH = "Bullish"
BEARISH = "Bearish"
ENTER_CALL = "Enter Call"
EXIT_CALL = "Exit Call"
ENTER_PUT = "Enter Put"
EXIT_PUT = "Exit Put"
CANCEL_PUT = "Cancel Put"
CANCEL_CALL = "Cancel Call"
CANCEL_TRADE = "Cancel Trade"
PREVIOUS_TRADE = "Previous Trade"
RESET_PREVIOUS_TRADE = 'RESET'

# Market Conditions
TRENDING = "Trending"
SIDEWAYS = "Sideways"
TRENDS = [ENTER_CALL, EXIT_CALL, ENTER_PUT, EXIT_PUT]
ALL_TRENDS = {*TRENDS, BULLISH, BEARISH}
PRICE_TYPES = ['Open', 'High', 'Low', 'Close', 'Open/Close', 'High/Low']

# Operators for Conditions
OPERATORS = ['>', '<', '>=', '<=', '==', '!=']

# Option Types
CALL = "Call"
PUT = "Put"

# Stop Loss and Trailing Types
TRAILING = 1
STOP = 2

# Bot Modes
BACK = "Backtest"
SIM = "Simulation"
LIVE = "Live"
OPTI = "Optimizer"

# Response Status
OK = 'ok'
ERROR = 'error'

# Order Sides
SIDE_BUY = 1
SIDE_SELL = -1

# Order Types
LIMIT_ORDER_TYPE = 1
MARKET_ORDER_TYPE = 2
STOPLOSS_MARKET_ORDER_TYPE = 3
STOPLOSS_LIMIT_ORDER_TYPE = 4

# Product Types
PRODUCT_TYPE_CNC = 'CNC'
PRODUCT_TYPE_INTRADAY = 'INTRADAY'
PRODUCT_TYPE_MARGIN = 'MARGIN'

# HTTP Status Codes
CODE_OK = 200

# Bot Operation Type
BOT_TYPE = LIVE

# Order Status
ORDER_OPEN = 'OPEN'
ORDER_CLOSED = 'CLOSED'
ORDER_REJECTED = 'REJECTED'

# Price Directions
POSITIVE = '+'
NEGATIVE = '-'

# Trade Actions
ENTER_LONG = "Enter Long"
EXIT_LONG = "Exit Long"
ENTER_SHORT = "Enter Short"
EXIT_SHORT = "Exit Short"

# Log Path
LOG_PATH = os.path.join(os.getcwd(), 'Data')
CONFIG_PATH = os.path.join(os.getcwd(), 'config')

ORDER_STATUS_CONFIRMED = 2
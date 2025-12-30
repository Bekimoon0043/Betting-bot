# config.py - FULLY OPTIMIZED VERSION
BOT_TOKEN = "7572288224:AAE4Dqejx2Rk0Y8wa9_u0-idU2S_vnbQwEg"
API_KEY = "ccc9d01accae841ab12893f72c0e9bb6"

BASE_URL = "https://v3.football.api-sports.io"

START_BALANCE = 1000

MIN_BET = 10
MAX_BET = 500

# ==============================================
# API OPTIMIZATION SETTINGS (NEW - MOST IMPORTANT)
# ==============================================
MAX_DAILY_API_REQUESTS = 100          # Hard limit from provider
API_PRIORITY_RESERVED_FOR_USERS = 70  # Reserve 70% for user interactions
MAX_BACKGROUND_REQUESTS = 30          # Use only 30% for background tasks

# Caching Times (Extended)
ODDS_CACHE_HOURS = 6                  # Cache odds for 6 hours
FIXTURES_CACHE_HOURS = 24             # Cache fixtures for 24 hours
RESULTS_CACHE_DAYS = 3                # Cache results for 3 days
LEAGUES_CACHE_DAYS = 30               # Cache leagues for 30 days

# ==============================================
# SCHEDULER OPTIMIZATION (REDUCED FREQUENCY)
# ==============================================
FETCH_INTERVAL_HOURS = 12             # Reduced from hourly to 12 hours
FIXTURE_UPDATE_HOURS = 12             # Update fixtures every 12 hours
RESULTS_UPDATE_HOURS = 6              # Check results every 6 hours
BET_SETTLEMENT_HOURS = 4              # Settle bets every 4 hours
CACHE_CLEANUP_HOURS = 24              # Clean cache once daily

# ==============================================
# LIMITS TO REDUCE API CALLS
# ==============================================
MAX_LEAGUES_TO_FETCH = 2              # Fetch only 2 leagues (was 3)
MAX_FIXTURES_PER_LEAGUE = 15          # Limit fixtures per league
MAX_DAYS_TO_FETCH = 1                 # Fetch only 1 day ahead (was 2)
MAX_API_CALLS_PER_RUN = 5             # Maximum API calls per scheduler run

# ==============================================
# ADMIN & FINANCIAL SETTINGS
# ==============================================
ADMIN_USER_ID = 6546621672            # Your Telegram user ID
TELEBIRR_ACCOUNT = "0978494843"
CBE_ACCOUNT = "1000475794978"

MIN_DEPOSIT = 50                      # Minimum deposit amount
MIN_WITHDRAWAL = 100                  # Minimum withdrawal amount

# ==============================================
# LEAGUE & NAVIGATION SETTINGS
# ==============================================
MAX_LEAGUES_PER_PAGE = 15
MAX_MATCHES_PER_LEAGUE = 30
ENABLE_SEARCH_FUNCTIONALITY = True

# Default active leagues (reduce to most popular)
DEFAULT_ACTIVE_LEAGUES = [39, 140, 135, 78, 61]  # Premier League, La Liga, Serie A, Bundesliga, Ligue 1

# ==============================================
# CACHE MANAGEMENT
# ==============================================
API_CACHE_HOURS = 24                  # Cache general API data for 24 hours
ODDS_CACHE_MINUTES = 60               # Cache odds for 60 minutes (user session)
API_CACHE_ENABLED = True              # Enable caching system

# ==============================================
# ODDS ADJUSTMENT SETTINGS
# ==============================================
ODDS_ADJUSTMENT = 0.15                # Subtract this from every odd
MINIMUM_ODDS = 1.10                   # Don't go below this minimum
ODDS_ROUNDING = 2                     # Decimal places for odds display

# ==============================================
# TIME-BASED MATCH FILTERING
# ==============================================
MATCH_GRACE_PERIOD_MINUTES = 15       # Hide matches that started more than 15 minutes ago
MATCH_FUTURE_LIMIT_HOURS = 24         # Show matches up to 24 hours in future (was 48)

# ==============================================
# RESULTS DATABASE SETTINGS
# ==============================================
RESULTS_STORAGE_DAYS = 3              # Store results for 3 days (was 2)
RESULTS_UPDATE_INTERVAL = 6           # Check results every 6 hours (was 2)

# ==============================================
# BOT BEHAVIOR SETTINGS
# ==============================================
ENABLE_BACKUP_API_KEY = False         # Don't use multiple keys (causes blocking)
MAX_RETRY_ATTEMPTS = 2                # Retry failed API calls max 2 times
RETRY_DELAY_SECONDS = 5               # Wait 5 seconds before retry

# ==============================================
# PERFORMANCE SETTINGS
# ==============================================
ENABLE_BATCH_PROCESSING = True        # Process multiple items at once
BATCH_SIZE = 3                        # Process 3 items per batch
REQUEST_DELAY_SECONDS = 1             # 1 second delay between API calls

# ==============================================
# LOGGING & MONITORING
# ==============================================
LOG_API_REQUESTS = True               # Log every API request
API_WARNING_THRESHOLD = 80            # Warn when 80% of daily limit used
API_CRITICAL_THRESHOLD = 90           # Enter emergency mode at 90%

# ==============================================
# EMERGENCY MODE SETTINGS
# ==============================================
ENABLE_EMERGENCY_MODE = True          # Enable when API limit is almost reached
EMERGENCY_MODE_THRESHOLD = 95         # Enter emergency mode at 95% usage
EMERGENCY_FALLBACK_LEAGUES = [39, 140]  # Only show Premier League & La Liga in emergency

# ==============================================
# USER EXPERIENCE SETTINGS
# ==============================================
SHOW_API_USAGE_TO_USERS = True        # Let users see API usage with /apistats
ENABLE_PREDICTIVE_CACHING = True      # Pre-cache popular matches
POPULAR_LEAGUE_IDS = [39, 140, 135]   # Pre-cache these leagues

# ==============================================
# DATABASE OPTIMIZATION
# ==============================================
ENABLE_DB_CLEANUP = True              # Auto-clean old records
DB_CLEANUP_DAYS = 7                   # Clean records older than 7 days
MAX_DB_CONNECTIONS = 5                # Maximum database connections

# ==============================================
# TELEGRAM BOT SETTINGS
# ==============================================
MAX_MESSAGE_LENGTH = 4000             # Telegram message limit
ENABLE_INLINE_KEYBOARDS = True        # Use inline keyboards
UPDATE_INTERVAL_SECONDS = 30          # How often to check for updates

# ==============================================
# DEBUG SETTINGS
# ==============================================
DEBUG_MODE = False                    # Enable debug logging
LOG_ALL_API_CALLS = False             # Log every API call (verbose)
SHOW_TIMING = False                   # Show how long operations take

# ==============================================
# NEW FEATURE SETTINGS
# ==============================================
ENABLE_MATCH_PREDICTIONS = False      # Not implemented yet
ENABLE_LIVE_SCORES = False            # Not implemented yet (uses many API calls)
ENABLE_TEAM_STATS = False             # Not implemented yet

# ==============================================
# SECURITY SETTINGS
# ==============================================
ENABLE_RATE_LIMITING = True           # Prevent spam
MAX_REQUESTS_PER_MINUTE = 30          # Per user rate limit
BLOCK_SUSPICIOUS_ACTIVITY = True      # Auto-block suspicious users
# bot.py
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)
import os
import uuid
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

# UPDATED: Changed import to use fetch_match_odds instead of fetch_1x2_odds
from cache_manager import cache
from config import BOT_TOKEN, START_BALANCE, ADMIN_USER_ID, TELEBIRR_ACCOUNT, CBE_ACCOUNT, MIN_DEPOSIT, MIN_WITHDRAWAL, MAX_LEAGUES_PER_PAGE, DEFAULT_ACTIVE_LEAGUES, MATCH_GRACE_PERIOD_MINUTES, ODDS_ADJUSTMENT
from db import init_db, cursor, conn
from scheduler import start_scheduler
from api import fetch_match_odds, fetch_fixture_result, fetch_leagues, fetch_league_fixtures
from betting import (
    add_selection,
    get_betslip,
    calculate_total_odds,
    place_bet,
    clear_betslip,
    remove_selection,
    get_matches_by_league,
    get_popular_leagues,
    get_league_info
)

# NEW: Import results database
from results_db import results_db

# ======================
# IMAGE HANDLING FUNCTIONS - UPDATED WITH PROPER ERROR HANDLING
# ======================
def ensure_image_directory():
    """Create image directory if it doesn't exist"""
    os.makedirs("transaction_images", exist_ok=True)

async def save_transaction_image(photo_file, transaction_id, user_id):
    """Save transaction image to file with validation and return filename"""
    ensure_image_directory()
    
    # Validate file size and type
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp']
    
    try:
        # Check file size if available
        if hasattr(photo_file, 'file_size') and photo_file.file_size > MAX_FILE_SIZE:
            raise ValueError(f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB")
        
        # Generate unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_ext = '.jpg'  # Default extension
        filename = f"deposit_{user_id}_{transaction_id}_{timestamp}{file_ext}"
        filepath = os.path.join("transaction_images", filename)
        
        # Download and save the image - USE AWAIT
        await photo_file.download_to_drive(filepath)
        
        # Verify file was saved
        if not os.path.exists(filepath):
            raise IOError("Failed to save image file")
        
        # Check file size after download
        file_size = os.path.getsize(filepath)
        if file_size == 0:
            os.remove(filepath)
            raise ValueError("Downloaded file is empty")
        
        if file_size > MAX_FILE_SIZE:
            os.remove(filepath)
            raise ValueError(f"File too large after download: {file_size // 1024}KB")
        
        print(f"✅ Saved transaction image: {filename} ({file_size // 1024}KB)")
        return filename
        
    except Exception as e:
        print(f"❌ Error saving image file: {e}")
        # Clean up any partial file
        if 'filepath' in locals() and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except:
                pass
        return None

def delete_transaction_image(filename):
    """Delete transaction image file"""
    try:
        if filename:
            filepath = os.path.join("transaction_images", filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                print(f"✅ Deleted image file: {filename}")
                return True
    except Exception as e:
        print(f"❌ Error deleting image file {filename}: {e}")
    return False

async def apistats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show API usage statistics"""
    try:
        from api_limiter import api_limiter
        stats = api_limiter.get_today_stats()
        
        text = f"📊 *API Usage Today*\n\n"
        text += f"• Requests Used: `{stats['used']}/100`\n"
        text += f"• Remaining: `{stats['remaining']}`\n"
        text += f"• Usage: `{stats['percentage']:.1f}%`\n\n"
        
        if stats['remaining'] < 20:
            text += "⚠️ *Warning:* API usage is high\n"
            text += "Some features may be limited until tomorrow.\n\n"
        
        text += "🔄 Resets at midnight (00:00 UTC)"
        
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Error getting API stats: {e}")
        
def get_image_file(filename):
    """Get image file object"""
    if not filename:
        return None
    
    try:
        filepath = os.path.join("transaction_images", filename)
        if os.path.exists(filepath):
            return open(filepath, 'rb')
        else:
            print(f"❌ Image file not found: {filepath}")
            return None
    except Exception as e:
        print(f"❌ Error opening image file {filename}: {e}")
        return None
async def apistats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show API usage statistics"""
    from api_limiter import api_limiter
    stats = api_limiter.get_today_stats()
    
    text = f"📊 *API Usage Today*\n\n"
    text += f"• Requests Used: `{stats['used']}/100`\n"
    text += f"• Remaining: `{stats['remaining']}`\n"
    text += f"• Usage: `{stats['percentage']:.1f}%`\n\n"
    
    if stats['remaining'] < 20:
        text += "⚠️ *Warning:* API usage is high\n"
    
    text += "🔄 Resets at midnight (00:00 UTC)"
    await update.message.reply_text(text, parse_mode="Markdown")
def cleanup_old_images():
    """Clean up old processed transaction images (optional)"""
    ensure_image_directory()
    
    # Get all processed transaction image filenames from database
    cursor.execute("SELECT image_filename FROM transactions WHERE status != 'pending' AND image_filename IS NOT NULL")
    processed_images = cursor.fetchall()
    
    deleted_count = 0
    for (filename,) in processed_images:
        if delete_transaction_image(filename):
            deleted_count += 1
    
    print(f"🧹 Cleaned up {deleted_count} old transaction images")

# ======================
# HELPER FUNCTIONS
# ======================
def get_country_flag(country_name: str) -> str:
    """Get appropriate flag emoji for country"""
    flag_map = {
        # Comprehensive country flag mapping
        "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "Spain": "🇪🇸", 
        "Italy": "🇮🇹",
        "Germany": "🇩🇪",
        "France": "🇫🇷",
        "Portugal": "🇵🇹",
        "Netherlands": "🇳🇱",
        "Brazil": "🇧🇷",
        "Argentina": "🇦🇷",
        "USA": "🇺🇸",
        "Mexico": "🇲🇽",
        "Turkey": "🇹🇷",
        "Russia": "🇷🇺",
        "Ukraine": "🇺🇦",
        "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
        "Belgium": "🇧🇪",
        "Austria": "🇦🇹",
        "Switzerland": "🇨🇭",
        "Denmark": "🇩🇰",
        "Sweden": "🇸🇪",
        "Norway": "🇳🇴",
        "Finland": "🇫🇮",
        "Poland": "🇵🇱",
        "Czech": "🇨🇿",
        "Croatia": "🇭🇷",
        "Serbia": "🇷🇸",
        "Greece": "🇬🇷",
        "Cyprus": "🇨🇾",
        "Israel": "🇮🇱",
        "Saudi": "🇸🇦",
        "UAE": "🇦🇪",
        "Qatar": "🇶🇦",
        "Canada": "🇨🇦",
        "Australia": "🇦🇺",
        "Japan": "🇯🇵",
        "Korea": "🇰🇷",
        "China": "🇨🇳",
        "International": "🌍",
        "World": "🌎",
        "Europe": "🇪🇺",
        "Africa": "🇦🇴",
        "Asia": "🇦🇸",
        "America": "🇺🇸"
    }
    
    # Check for exact match
    if country_name in flag_map:
        return flag_map[country_name]
    
    # Check for partial matches
    for key, flag in flag_map.items():
        if key in country_name or country_name in key:
            return flag
    
    # Use country code as fallback
    if country_name and len(country_name) >= 2:
        return f"({country_name[:2].upper()})"
    
    return "🏆"

# ======================
# DEBUG ODDS COMMAND
# ======================
async def debug_odds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Debug command to check odds adjustment"""
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Admin only")
        return
    
    from config import ODDS_ADJUSTMENT, MINIMUM_ODDS, ODDS_ROUNDING
    from api import adjust_odds
    
    text = f"📊 *Odds Adjustment Debug*\n\n"
    text += f"• Adjustment: -{ODDS_ADJUSTMENT}\n"
    text += f"• Minimum Odds: {MINIMUM_ODDS}\n"
    text += f"• Rounding: {ODDS_ROUNDING} decimals\n\n"
    
    # Test with some examples
    examples = [1.50, 2.00, 3.50, 1.20, 10.00, 1.05]
    
    text += "*Example Adjustments:*\n"
    for original in examples:
        adjusted = adjust_odds(original)
        difference = original - adjusted if adjusted else 0
        text += f"• {original:.2f} → {adjusted:.2f} (diff: {difference:.2f})\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")

# ======================
# MAIN MENU - UPDATED FOR LEAGUE-FIRST NAVIGATION
# ======================
def get_main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🏆 Today's Leagues", callback_data="menu_leagues_today")],
        [InlineKeyboardButton("🏆 Tomorrow's Leagues", callback_data="menu_leagues_tomorrow")],
        [InlineKeyboardButton("🎫 My Bet Slip", callback_data="menu_betslip")],
        [InlineKeyboardButton("💰 My Balance", callback_data="menu_balance")],
        [InlineKeyboardButton("📊 My Bets", callback_data="menu_mybets")],
        [
            InlineKeyboardButton("📥 Deposit", callback_data="menu_deposit"),
            InlineKeyboardButton("📤 Withdraw", callback_data="menu_withdraw")
        ],
        [InlineKeyboardButton("📊 Match Results", callback_data="menu_results")],
    ]
    return InlineKeyboardMarkup(keyboard)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str = "⚽ *Football Betting Bot*"):
    if update.callback_query:
        await update.callback_query.edit_message_text(
            message,
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            message,
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )

# ======================
# /start
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    cursor.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (user_id, username, balance) VALUES (?, ?, ?)",
            (user.id, user.username, START_BALANCE)
        )
        conn.commit()

    await show_main_menu(update, context, f"⚽ *Welcome {user.first_name}!*\n\n*Football Betting Bot*")

# ======================
# MAIN MENU HANDLER - UPDATED FOR PAGINATION
# ======================
# ======================
# MAIN MENU HANDLER - UPDATED FOR PAGINATION
# ======================
async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    # Handle league types
    if data.startswith("leagues_type_"):
        await show_league_types(update, context)
        return
    
    # Existing handlers
    if data == "menu_leagues_today":
        await show_leagues_menu(update, context, day_offset=0, page=0)
    elif data == "menu_leagues_tomorrow":
        await show_leagues_menu(update, context, day_offset=1, page=0)
    elif data.startswith("league_"):
        # league_{league_id}_{day_offset}_{page}
        parts = data.split("_")
        if len(parts) >= 4:
            league_id = int(parts[1])
            day_offset = int(parts[2])
            page = int(parts[3])
            await show_league_matches(update, context, league_id, day_offset, page)
    elif data == "menu_betslip":
        await show_betslip_inline(query)
    elif data == "menu_balance":
        await show_balance_inline(query)
    elif data == "menu_mybets":
        context.user_data["bet_page"] = 1
        await show_my_bets_inline(query)
    elif data == "menu_deposit":
        await show_deposit_methods(query, context)
    elif data == "menu_withdraw":
        await start_withdraw(update, context)
    elif data == "menu_results":
        await results_command(update, context)
    elif data == "back_main":
        await show_main_menu(update, context)
    elif data == "back_leagues":
        # Try to get day_offset and page from context or default
        day_offset = context.user_data.get("last_day_offset", 0)
        page = context.user_data.get("last_leagues_page", 0)
        await show_leagues_menu(update, context, day_offset=day_offset, page=page)
    elif data == "back_deposit":
        await show_deposit_methods(query, context)
    elif data == "search_matches":
        await search_matches(update, context)
    elif data == "search_team":
        await handle_search_team(update, context)
# ======================
# LEAGUE TYPES SELECTION
# ======================
async def show_league_types(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show different types of competitions"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🏆 Top Leagues", callback_data="leagues_type_top")],
        [InlineKeyboardButton("🏅 Domestic Cups", callback_data="leagues_type_cups")],
        [InlineKeyboardButton("🌍 International", callback_data="leagues_type_intl")],
        [InlineKeyboardButton("⭐ Popular", callback_data="leagues_type_popular")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
    ]
    
    await query.edit_message_text(
        "🏆 *Select Competition Type*\n\nChoose the type of competitions you want to view:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ======================
# LEAGUE-FIRST NAVIGATION FUNCTIONS WITH PAGINATION
# ======================
async def show_leagues_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, day_offset=0, page=0):
    """Show available leagues for a specific day"""
    # If called from callback, extract parameters from callback data
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        
        # If callback data starts with leagues_page_ or refresh_leagues_
        if query.data.startswith("leagues_page_") or query.data.startswith("refresh_leagues_"):
            # Extract day_offset and page from callback data
            parts = query.data.split("_")
            if len(parts) >= 4:
                day_offset = int(parts[2])
                page = int(parts[3])
    
    # Store day_offset in context for back navigation
    context.user_data["last_day_offset"] = day_offset
    
    # Initialize variables
    total_leagues = 0
    total_pages = 0
    
    # Get target date
    target_date = (datetime.now() + timedelta(days=day_offset)).strftime("%Y-%m-%d")
    
    try:
        # First, get total count for pagination
        cursor.execute(f"""
            SELECT COUNT(DISTINCT l.league_id) as total_leagues
            FROM leagues l
            JOIN fixtures f ON l.league_id = f.league_id
            WHERE date(f.start_time) = date(?)
            AND f.status = 'NS'
            AND datetime(f.start_time) > datetime('now', '-{MATCH_GRACE_PERIOD_MINUTES} minutes')
            AND l.is_active = 1
        """, (target_date,))
        
        total_result = cursor.fetchone()
        total_leagues = total_result[0] if total_result else 0
        
        # Calculate total pages - FIXED: Check for division by zero
        if total_leagues > 0:
            total_pages = (total_leagues + MAX_LEAGUES_PER_PAGE - 1) // MAX_LEAGUES_PER_PAGE
        else:
            total_pages = 0
        
        # Make sure page is within bounds
        if total_pages > 0:
            page = max(0, min(page, total_pages - 1))
        else:
            page = 0
        
        print(f"[Leagues Menu] Total leagues found: {total_leagues}, Pages: {total_pages}, Current Page: {page}")
        
    except Exception as e:
        print(f"[Leagues Menu] Error counting leagues: {e}")
        # Use a simpler query as fallback
        cursor.execute("""
            SELECT COUNT(DISTINCT league_id) as total_leagues
            FROM fixtures 
            WHERE date(start_time) = date(?)
            AND status = 'NS'
        """, (target_date,))
        total_result = cursor.fetchone()
        total_leagues = total_result[0] if total_result else 0
        total_pages = 1 if total_leagues > 0 else 0
        page = 0
    
    # Get leagues that have matches on this day
    cursor.execute(f"""
        SELECT DISTINCT l.league_id, l.name, l.country, l.logo_url,
               COUNT(f.fixture_id) as match_count
        FROM leagues l
        JOIN fixtures f ON l.league_id = f.league_id
        WHERE date(f.start_time) = date(?)
        AND f.status = 'NS'
        AND datetime(f.start_time) > datetime('now', '-{MATCH_GRACE_PERIOD_MINUTES} minutes')
        AND l.is_active = 1
        GROUP BY l.league_id
        ORDER BY l.country, l.name
        LIMIT ? OFFSET ?
    """, (target_date, MAX_LEAGUES_PER_PAGE, page * MAX_LEAGUES_PER_PAGE))
    
    leagues = cursor.fetchall()
    
    # If no leagues found, try to get popular leagues as fallback
    if not leagues and page == 0:
        print(f"[Leagues Menu] No leagues found for {target_date}, trying popular leagues...")
        cursor.execute(f"""
            SELECT l.league_id, l.name, l.country, l.logo_url,
                   COUNT(f.fixture_id) as match_count
            FROM leagues l
            JOIN fixtures f ON l.league_id = f.league_id
            WHERE f.status = 'NS'
            AND datetime(f.start_time) > datetime('now')
            AND l.league_id IN ({",".join(map(str, DEFAULT_ACTIVE_LEAGUES))})
            GROUP BY l.league_id
            ORDER BY match_count DESC
            LIMIT ?
        """, (MAX_LEAGUES_PER_PAGE,))
        
        leagues = cursor.fetchall()
        total_leagues = len(leagues)
        total_pages = 1 if leagues else 0
        print(f"[Leagues Menu] Found {len(leagues)} popular leagues as fallback")
    
    if not leagues:
        day_name = "today" if day_offset == 0 else "tomorrow"
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_leagues_{day_offset}_{page}")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
        ]
        
        message = f"🏆 *No {day_name}'s matches available*\n\nNo leagues have scheduled matches for {day_name}. Please check back later!"
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                message, 
                parse_mode="Markdown", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                message, 
                parse_mode="Markdown", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return
    
    # Create keyboard with leagues
    keyboard = []
    current_country = None
    
    for league_id, name, country, logo_url, match_count in leagues:
        # Add country header if it's a new country
        if country != current_country:
            # Don't add header for first item
            if current_country is not None:
                keyboard.append([])  # Empty row for spacing
            current_country = country
        
        # Country flag
        flag = get_country_flag(country)
        
        # Truncate long league names
        display_name = name[:20] + "..." if len(name) > 20 else name
        
        keyboard.append([
            InlineKeyboardButton(
                f"{flag} {display_name} ({match_count})",
                callback_data=f"league_{league_id}_{day_offset}_{page}"
            )
        ])
    
    # Add pagination buttons - Only show if there are multiple pages
    pagination_row = []
    
    if total_pages > 1:
        if page > 0:
            pagination_row.append(
                InlineKeyboardButton("⬅️ Previous", callback_data=f"leagues_page_{day_offset}_{page-1}")
            )
        
        # Add page indicator (non-clickable)
        pagination_row.append(
            InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="noop")
        )
        
        if page < total_pages - 1:
            pagination_row.append(
                InlineKeyboardButton("Next ➡️", callback_data=f"leagues_page_{day_offset}_{page+1}")
            )
    
    if pagination_row:
        keyboard.append(pagination_row)
    
    # Add navigation buttons
    if day_offset == 0:
        keyboard.append([InlineKeyboardButton("📅 View Tomorrow's Leagues", callback_data="menu_leagues_tomorrow")])
    else:
        keyboard.append([InlineKeyboardButton("⚽ View Today's Leagues", callback_data="menu_leagues_today")])
    
    keyboard.append([InlineKeyboardButton("🔍 Search Matches", callback_data="search_matches")])
    keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")])
    
    day_name = "Today" if day_offset == 0 else "Tomorrow"
    page_info = f" (Page {page+1}/{total_pages})" if total_pages > 1 else ""
    message = f"🏆 *{day_name}'s Football Leagues{page_info}*\n\nSelect a league to view available matches:"
    
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                message, 
                parse_mode="Markdown", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            print(f"[Leagues Menu] Error editing message: {e}")
            # Try to send a new message instead
            await update.callback_query.message.reply_text(
                message,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    else:
        await update.message.reply_text(
            message, 
            parse_mode="Markdown", 
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def show_league_matches(update: Update, context: ContextTypes.DEFAULT_TYPE, league_id: int = None, day_offset: int = 0, page: int = 0):
    """Show matches for a specific league with pagination"""
    query = update.callback_query
    await query.answer()
    
    # If league_id not provided, get it from callback data
    if league_id is None:
        # Parse callback data: league_{league_id}_{day_offset}_{page}
        data_parts = query.data.split("_")
        if len(data_parts) < 4:
            await query.edit_message_text("❌ Error loading league matches")
            return
        league_id = int(data_parts[1])
        day_offset = int(data_parts[2])
        page = int(data_parts[3])
    
    # Store page in context for back navigation
    context.user_data["last_leagues_page"] = page
    
    # Get league info
    cursor.execute("SELECT name, country FROM leagues WHERE league_id = ?", (league_id,))
    league_info = cursor.fetchone()
    
    if not league_info:
        await query.edit_message_text("❌ League not found")
        return
    
    league_name, country = league_info
    target_date = (datetime.now() + timedelta(days=day_offset)).strftime("%Y-%m-%d")
    
    # Get matches for this league on the specific day
    cursor.execute(f"""
        SELECT f.fixture_id, t1.name as home, t2.name as away, 
               f.start_time, t1.logo_url as home_logo, t2.logo_url as away_logo
        FROM fixtures f
        JOIN teams t1 ON f.home_team_id = t1.team_id
        JOIN teams t2 ON f.away_team_id = t2.team_id
        WHERE f.league_id = ? 
        AND date(f.start_time) = date(?)
        AND f.status = 'NS'
        AND datetime(f.start_time) > datetime('now', '-{MATCH_GRACE_PERIOD_MINUTES} minutes')
        ORDER BY f.start_time
        LIMIT 30
    """, (league_id, target_date))
    
    matches = cursor.fetchall()
    
    if not matches:
        day_name = "today" if day_offset == 0 else "tomorrow"
        keyboard = [
            [InlineKeyboardButton(f"🔙 Back to {day_name}'s Leagues", 
                                 callback_data=f"leagues_page_{day_offset}_{page}")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
        ]
        
        await query.edit_message_text(
            f"🏟 *{league_name}*\n🌍 {country}\n\nNo matches available for {day_name}. Please check back later!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Format matches with team logos and times
    text = f"🏟 *{league_name}*\n🌍 {country}\n📅 {target_date}\n\n*Available Matches ({len(matches)}):*\n"
    keyboard = []
    
    for i, (fixture_id, home, away, start_time, home_logo, away_logo) in enumerate(matches, 1):
        # Format time
        try:
            dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            time_str = dt.strftime("%H:%M")
            time_emoji = "🌙" if dt.hour >= 18 else "☀️" if dt.hour >= 12 else "🌅"
        except:
            time_str = start_time[11:16] if len(start_time) > 11 else start_time
            time_emoji = "🕐"
        
        # Create match button (truncate long names)
        home_display = home[:12] + "..." if len(home) > 12 else home
        away_display = away[:12] + "..." if len(away) > 12 else away
        
        keyboard.append([
            InlineKeyboardButton(
                f"{time_emoji} {time_str} | {home_display} vs {away_display}",
                callback_data=f"match_{fixture_id}"
            )
        ])
        
        # Add to text preview
        text += f"{i}. {time_str} - {home} vs {away}\n"
    
    # Add navigation buttons
    keyboard.append([
        InlineKeyboardButton("🔄 Refresh Matches", callback_data=f"league_{league_id}_{day_offset}_{page}"),
        InlineKeyboardButton("📊 View League Info", callback_data=f"league_info_{league_id}")
    ])
    
    keyboard.append([
        InlineKeyboardButton("🔙 Back to Leagues", 
                           callback_data=f"leagues_page_{day_offset}_{page}"),
        InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")
    ])
    
    # Check if message is too long
    if len(text) > 4000:
        text = text[:4000] + "\n\n... (too many matches to list)"
    
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def match_details_with_odds(update: Update, context: ContextTypes.DEFAULT_TYPE, fixture_id: int = None):
    """Show match details with betting odds - Updated for league structure"""
    query = update.callback_query
    await query.answer()
    
    # If fixture_id is not provided, get it from callback data
    if fixture_id is None:
        try:
            data_parts = query.data.split("_")
            if data_parts[0] == "refresh" and data_parts[1] == "odds":
                fixture_id = int(data_parts[2])
            else:
                fixture_id = int(query.data.split("_")[1])
        except (IndexError, ValueError) as e:
            print(f"Error parsing fixture_id: {e}, data: {query.data}")
            await query.edit_message_text("❌ Error loading match details")
            return
    
    # Get match details with league info
    try:
        cursor.execute("""
            SELECT f.league_id, f.home_team_id, f.away_team_id, f.start_time, f.status,
                   t1.name as home_name, t2.name as away_name,
                   l.name as league_name, l.country,
                   t1.logo_url as home_logo, t2.logo_url as away_logo
            FROM fixtures f
            JOIN teams t1 ON f.home_team_id = t1.team_id
            JOIN teams t2 ON f.away_team_id = t2.team_id
            JOIN leagues l ON f.league_id = l.league_id
            WHERE f.fixture_id = ?
        """, (fixture_id,))
        
        match = cursor.fetchone()
    except Exception as e:
        print(f"Database error in match_details_with_odds: {e}")
        await query.edit_message_text("❌ Database error. Please try again.")
        return
    
    if not match:
        await query.edit_message_text("❌ Match not found")
        return
    
    (league_id, home_id, away_id, start_time, status, home_name, away_name, 
     league_name, country, home_logo, away_logo) = match
    
    # Check if match has already started or finished
    if status != 'NS':
        keyboard = [
            [InlineKeyboardButton("🔙 Back to League", callback_data=f"league_{league_id}_0_0")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
        ]
        
        status_text = {
            'LIVE': 'live',
            'HT': 'half-time',
            'FT': 'finished',
            'CANCELED': 'canceled',
            'POSTPONED': 'postponed'
        }.get(status, 'in progress')
        
        await query.edit_message_text(
            f"⚠️ *Match Status Update*\n\n"
            f"⚽ {home_name} vs {away_name}\n"
            f"🏆 {league_name}\n\n"
            f"This match is already {status_text}.\n"
            f"Betting is no longer available for this match.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # TIME-BASED CHECK
    if status == 'NS':
        try:
            # Parse the start time
            start_str = start_time.replace('Z', '+00:00')
            match_start = datetime.fromisoformat(start_str)
            now_utc = datetime.now(timezone.utc)
            
            # Calculate how many minutes overdue
            if now_utc > match_start:
                overdue_minutes = (now_utc - match_start).total_seconds() / 60
                
                # If match is too overdue, hide betting
                if overdue_minutes > MATCH_GRACE_PERIOD_MINUTES:
                    keyboard = [
                        [InlineKeyboardButton("🔙 Back to League", callback_data=f"league_{league_id}_0_0")],
                        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
                    ]
                    
                    await query.edit_message_text(
                        f"⏰ *Match Time Update*\n\n"
                        f"⚽ {home_name} vs {away_name}\n"
                        f"🏆 {league_name}\n\n"
                        f"📅 Scheduled: {match_start.strftime('%H:%M')} UTC\n"
                        f"⏰ Current: {now_utc.strftime('%H:%M')} UTC\n"
                        f"📊 Status: Should have started ({overdue_minutes:.0f} minutes ago)\n\n"
                        f"❌ **Betting is no longer available**\n"
                        f"This match has likely started or been delayed.",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    return
                    
        except Exception as e:
            print(f"[Time Check] Error: {e}")
            # Continue if time check fails
    
    # Format time
    try:
        dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        time_str = dt.strftime("%H:%M")
        date_str = dt.strftime("%Y-%m-%d")
    except:
        time_str = start_time[11:16] if len(start_time) > 11 else start_time
        date_str = start_time[:10] if len(start_time) >= 10 else "Today"
    
    # Get odds
    odds_data = fetch_match_odds(fixture_id)
    
    if not odds_data or not odds_data["1x2"]:
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Odds", callback_data=f"refresh_odds_{fixture_id}")],
            [InlineKeyboardButton("🔙 Back to League", callback_data=f"league_{league_id}_0_0")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
        ]
        
        await query.edit_message_text(
            f"⚽ *{home_name} vs {away_name}*\n"
            f"🏆 {league_name}\n"
            f"🌍 {country}\n"
            f"📅 {date_str} ⏰ {time_str}\n\n"
            f"❌ *Odds temporarily unavailable*\n"
            f"Please try again in a few moments.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Store in context
    context.user_data["current_fixture"] = fixture_id
    context.user_data["current_odds"] = odds_data
    context.user_data["current_league_id"] = league_id
    
    # Format match info with emojis
    match_info = (
        f"⚽ *{home_name} vs {away_name}*\n"
        f"🏆 {league_name}\n"
        f"🌍 {country}\n"
        f"📅 {date_str} ⏰ {time_str}\n\n"
        f"📊 *Note:* Odds adjusted by -{ODDS_ADJUSTMENT}\n\n"
        f"🎯 *Select your prediction:*"
    )
    
    # Create betting keyboard
    keyboard = []
    o1x2 = odds_data["1x2"]
    
    # 1X2 Market Row
    home_display = home_name[:8] if len(home_name) > 8 else home_name
    away_display = away_name[:8] if len(away_name) > 8 else away_name
    
    keyboard.append([
        InlineKeyboardButton(f"🏠 {home_display}", callback_data=f"bet_{fixture_id}_1X2_1_{o1x2['home']}"),
        InlineKeyboardButton("🤝 DRAW", callback_data=f"bet_{fixture_id}_1X2_X_{o1x2['draw']}"),
        InlineKeyboardButton(f"✈️ {away_display}", callback_data=f"bet_{fixture_id}_1X2_2_{o1x2['away']}")
    ])
    
    # 1X2 Odds Row
    keyboard.append([
        InlineKeyboardButton(f"💰 {o1x2['home']:.2f}", callback_data=f"bet_{fixture_id}_1X2_1_{o1x2['home']}"),
        InlineKeyboardButton(f"💰 {o1x2['draw']:.2f}", callback_data=f"bet_{fixture_id}_1X2_X_{o1x2['draw']}"),
        InlineKeyboardButton(f"💰 {o1x2['away']:.2f}", callback_data=f"bet_{fixture_id}_1X2_2_{o1x2['away']}")
    ])
    
    # Over/Under Section
    if odds_data.get("ou"):
        keyboard.append([InlineKeyboardButton("───── ⚽ OVER/UNDER ─────", callback_data="ou_header")])
        
        ou = odds_data["ou"]
        ou_lines = {}
        
        # Group by line
        for key, odds in ou.items():
            if " " in key:
                line = key.split(" ")[1]
                if line not in ou_lines:
                    ou_lines[line] = {}
                if key.startswith("Over"):
                    ou_lines[line]["Over"] = odds
                elif key.startswith("Under"):
                    ou_lines[line]["Under"] = odds
        
        # Show most common lines
        for line in ['1.5', '2.5', '3.5']:
            if line in ou_lines:
                row = []
                if ou_lines[line].get("Over"):
                    row.append(InlineKeyboardButton(
                        f"⬆️ Over {line} ({ou_lines[line]['Over']:.2f})",
                        callback_data=f"bet_{fixture_id}_OU_Over {line}_{ou_lines[line]['Over']}"
                    ))
                if ou_lines[line].get("Under"):
                    row.append(InlineKeyboardButton(
                        f"⬇️ Under {line} ({ou_lines[line]['Under']:.2f})",
                        callback_data=f"bet_{fixture_id}_OU_Under {line}_{ou_lines[line]['Under']}"
                    ))
                if row:
                    keyboard.append(row)
    
    # Additional navigation
    keyboard.append([
        InlineKeyboardButton("🔙 Back to League", callback_data=f"league_{league_id}_0_0"),
        InlineKeyboardButton("🔄 Refresh Odds", callback_data=f"refresh_odds_{fixture_id}")
    ])
    
    keyboard.append([
        InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")
    ])
    
    await query.edit_message_text(
        match_info,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Update the match_callback to use new function
async def match_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle match selection - redirect to new detailed view"""
    await match_details_with_odds(update, context)

# Add search functionality
async def search_matches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search for matches by team name"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🔍 Search by Team Name", callback_data="search_team")],
        [InlineKeyboardButton("🔍 Browse All Leagues", callback_data="menu_leagues_today")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
    ]
    
    await query.edit_message_text(
        "🔍 *Search Matches*\n\nHow would you like to search?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_search_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle team search"""
    query = update.callback_query
    await query.answer()
    
    context.user_data["awaiting_team_search"] = True
    
    await query.edit_message_text(
        "🔍 *Search Teams*\n\nEnter the team name you want to search for:",
        parse_mode="Markdown"
    )

async def search_team_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle team search input - FIXED QUERY PARAMETER"""
    if not context.user_data.get("awaiting_team_search"):
        return
    
    search_term = update.message.text.strip()
    
    if len(search_term) < 3:
        await update.message.reply_text("❌ Please enter at least 3 characters")
        return
    
    # Search for teams - FIXED: Using proper parameter format
    cursor.execute(f"""
        SELECT t.team_id, t.name, COUNT(f.fixture_id) as match_count
        FROM teams t
        LEFT JOIN fixtures f ON t.team_id IN (f.home_team_id, f.away_team_id)
        WHERE t.name LIKE ? 
        AND f.status = 'NS'
        AND datetime(f.start_time) > datetime('now', '-{MATCH_GRACE_PERIOD_MINUTES} minutes')
        GROUP BY t.team_id
        ORDER BY match_count DESC
        LIMIT 10
    """, (f"%{search_term}%",))
    
    teams = cursor.fetchall()
    
    if not teams:
        keyboard = [
            [InlineKeyboardButton("🔍 Search Again", callback_data="search_team")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
        ]
        
        await update.message.reply_text(
            f"❌ No teams found for '{search_term}'\n\nTry a different search term.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    text = f"🔍 *Search Results for '{search_term}'*\n\n"
    keyboard = []
    
    for team_id, team_name, match_count in teams:
        # Get upcoming matches for this team
        cursor.execute(f"""
            SELECT f.fixture_id, 
                   CASE 
                       WHEN f.home_team_id = ? THEN t2.name 
                       ELSE t1.name 
                   END as opponent,
                   f.start_time, l.name as league_name
            FROM fixtures f
            JOIN teams t1 ON f.home_team_id = t1.team_id
            JOIN teams t2 ON f.away_team_id = t2.team_id
            JOIN leagues l ON f.league_id = l.league_id
            WHERE ? IN (f.home_team_id, f.away_team_id)
            AND f.status = 'NS'
            AND datetime(f.start_time) > datetime('now', '-{MATCH_GRACE_PERIOD_MINUTES} minutes')
            ORDER BY f.start_time
            LIMIT 3
        """, (team_id, team_id))
        
        matches = cursor.fetchall()
        
        text += f"⚽ *{team_name}*\n"
        
        if matches:
            for match in matches:
                fixture_id, opponent, start_time, league_name = match
                time_str = start_time[11:16] if len(start_time) > 11 else start_time
                text += f"   vs {opponent} - {time_str} ({league_name})\n"
                
                keyboard.append([
                    InlineKeyboardButton(
                        f"{team_name[:8]} vs {opponent[:8]}",
                        callback_data=f"match_{fixture_id}"
                    )
                ])
        else:
            text += f"   No upcoming matches\n"
        
        text += "\n"
    
    keyboard.append([
        InlineKeyboardButton("🔍 New Search", callback_data="search_team"),
        InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")
    ])
    
    context.user_data["awaiting_team_search"] = False
    
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ======================
# DEPOSIT SYSTEM
# ======================
async def show_deposit_methods(query, context):
    keyboard = [
        [
            InlineKeyboardButton("📱 Telebirr", callback_data="deposit_telebirr"),
            InlineKeyboardButton("🏦 CBE", callback_data="deposit_cbe")
        ],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_main")]
    ]
    
    await query.edit_message_text(
        "💰 *Choose Deposit Method:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_deposit_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    method = query.data.replace("deposit_", "")
    
    # Store method in context
    context.user_data["deposit_method"] = method
    
    if method == "telebirr":
        account = TELEBIRR_ACCOUNT
        method_name = "Telebirr"
    else:
        account = CBE_ACCOUNT
        method_name = "CBE"
    
    instructions = (
        f"💰 *{method_name} Deposit*\n\n"
        f"📱 *Account Number:* `{account}`\n"
        f"💵 *Minimum Deposit:* `{MIN_DEPOSIT}`\n\n"
        f"📝 *Instructions:*\n"
        f"1. Send money to the account above (minimum {MIN_DEPOSIT})\n"
        f"2. Take a screenshot of the payment\n"
        f"3. Send the screenshot here\n\n"
        f"⚠️ *Note:* Include amount in the screenshot"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Back to Methods", callback_data="back_deposit")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
    ]
    
    await query.edit_message_text(
        instructions,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Mark that we're awaiting screenshot
    context.user_data["awaiting_deposit_screenshot"] = True

async def handle_deposit_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle deposit screenshot from user"""
    if not context.user_data.get("awaiting_deposit_screenshot"):
        return
    
    user = update.effective_user
    method = context.user_data.get("deposit_method", "telebirr")
    
    # Get the photo file
    photo_file = await update.message.photo[-1].get_file()
    
    # Store photo file in context for later use
    context.user_data["deposit_photo_file"] = photo_file
    context.user_data["awaiting_deposit_screenshot"] = False
    context.user_data["awaiting_deposit_amount"] = True
    
    await update.message.reply_text(
        "✅ *Screenshot received!*\n\n"
        "Now please send me the amount you deposited:",
        parse_mode="Markdown"
    )

async def handle_deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle deposit amount input"""
    if not context.user_data.get("awaiting_deposit_amount"):
        return
    
    try:
        amount = float(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number")
        return
    
    if amount < MIN_DEPOSIT:  # Check minimum deposit
        await update.message.reply_text(f"❌ Minimum deposit is {MIN_DEPOSIT}")
        return
    
    user = update.effective_user
    method = context.user_data.get("deposit_method", "telebirr")
    photo_file = context.user_data.get("deposit_photo_file")
    
    if not photo_file:
        await update.message.reply_text("❌ Error: Screenshot not found. Please start over.")
        context.user_data["awaiting_deposit_amount"] = False
        context.user_data["deposit_photo_file"] = None
        context.user_data["deposit_method"] = None
        return
    
    # First, save the transaction to get transaction_id
    cursor.execute("""
        INSERT INTO transactions 
        (user_id, username, type, amount, method, status)
        VALUES (?, ?, 'deposit', ?, ?, 'pending')
    """, (user.id, user.username, amount, method))
    conn.commit()
    
    # Get transaction ID
    transaction_id = cursor.lastrowid
    
    # Save image to file - USE AWAIT
    try:
        image_filename = await save_transaction_image(photo_file, transaction_id, user.id)
        
        if image_filename:
            # Update transaction with image filename
            cursor.execute("""
                UPDATE transactions 
                SET image_filename = ?
                WHERE transaction_id = ?
            """, (image_filename, transaction_id))
            conn.commit()
        else:
            print(f"⚠️ Could not save image for transaction #{transaction_id}")
    except Exception as e:
        print(f"❌ Error saving image: {e}")
        image_filename = None
    
    # Notify admin with inline buttons
    method_name = "Telebirr" if method == "telebirr" else "CBE"
    
    admin_message = (
        f"📥 *NEW DEPOSIT REQUEST*\n\n"
        f"👤 User: @{user.username}\n"
        f"🆔 ID: `{user.id}`\n"
        f"💰 Amount: `{amount}`\n"
        f"📱 Method: {method_name}\n"
        f"📋 Transaction: #{transaction_id}\n\n"
        f"*Click buttons below to approve or reject:*"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ APPROVE", callback_data=f"approve_deposit_{transaction_id}"),
            InlineKeyboardButton("❌ REJECT", callback_data=f"reject_deposit_{transaction_id}")
        ]
    ]
    
    # Send notification to admin with saved image file
    try:
        if image_filename:
            image_file = get_image_file(image_filename)
            if image_file:
                await context.bot.send_photo(
                    chat_id=ADMIN_USER_ID,
                    photo=image_file,
                    caption=admin_message,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                image_file.close()
            else:
                # Send message without image if file not found
                await context.bot.send_message(
                    chat_id=ADMIN_USER_ID,
                    text=f"{admin_message}\n\n⚠️ *Note:* Screenshot file could not be loaded.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        else:
            # Send message without image
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=admin_message,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        print(f"✅ Sent deposit notification to admin {ADMIN_USER_ID}")
    except Exception as e:
        print(f"❌ Error sending to admin: {e}")
        # Try to send a simpler message
        try:
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=f"?? Deposit request from @{user.username} - Amount: {amount} - Transaction: #{transaction_id}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e2:
            print(f"❌ Failed to send even simple message: {e2}")
    
    # Clear the context
    context.user_data["awaiting_deposit_amount"] = False
    context.user_data["deposit_photo_file"] = None
    context.user_data["deposit_method"] = None
    
    await update.message.reply_text(
        "✅ *Deposit Request Sent!*\n\n"
        "Your deposit request has been sent to admin for approval.\n"
        "You will be notified when it's processed.",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )

# ======================
# WITHDRAWAL SYSTEM - UPDATED WITH IMMEDIATE DEDUCTION
# ======================
async def start_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start withdrawal process"""
    # Get query from either callback or message
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
    else:
        query = None
        user_id = update.effective_user.id
    
    # Check user balance first
    cursor.execute(
        "SELECT balance FROM users WHERE user_id=?",
        (user_id,)
    )
    row = cursor.fetchone()
    
    if not row:
        if query:
            await query.edit_message_text("❌ User not found")
        else:
            await update.message.reply_text("❌ User not found")
        return
    
    balance = row[0]
    
    if balance <= 0:
        keyboard = [
            [InlineKeyboardButton("📥 Make Deposit", callback_data="menu_deposit")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_main")]
        ]
        if query:
            await query.edit_message_text(
                "❌ *Insufficient Balance*\n\n"
                "You don't have enough balance for withdrawal.\n"
                "Please make a deposit first.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                "❌ *Insufficient Balance*\n\n"
                "You don't have enough balance for withdrawal.\n"
                "Please make a deposit first.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return
    
    # Ask for withdrawal method first
    keyboard = [
        [
            InlineKeyboardButton("📱 Telebirr", callback_data="withdraw_telebirr"),
            InlineKeyboardButton("🏦 CBE", callback_data="withdraw_cbe")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="back_main")]
    ]
    
    if query:
        await query.edit_message_text(
            f"💵 *Withdrawal*\n\n"
            f"💰 Available Balance: `{balance}` birr\n\n"
            f"*Select withdrawal method:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            f"💵 *Withdrawal*\n\n"
            f"💰 Available Balance: `{balance}` birr\n\n"
            f"*Select withdrawal method:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_withdraw_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdrawal method selection"""
    query = update.callback_query
    await query.answer()
    
    method = query.data.replace("withdraw_", "")
    user = query.from_user
    
    # Store method in context
    context.user_data["withdraw_method"] = method
    
    method_name = "Telebirr" if method == "telebirr" else "CBE"
    
    # Ask for account number
    context.user_data["awaiting_withdraw_account"] = True
    
    await query.edit_message_text(
        f"💵 *Withdrawal Method:* {method_name}\n\n"
        f"*Enter your {method_name} account number:*",
        parse_mode="Markdown"
    )

async def handle_withdraw_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdrawal account number"""
    if not context.user_data.get("awaiting_withdraw_account"):
        return
    
    account_number = update.message.text.strip()
    method = context.user_data.get("withdraw_method", "telebirr")
    user = update.effective_user
    
    if not account_number or len(account_number) < 5:
        await update.message.reply_text("❌ Please enter a valid account number")
        return
    
    # Store account number and move to amount input
    context.user_data["withdraw_account"] = account_number
    context.user_data["awaiting_withdraw_account"] = False
    context.user_data["awaiting_withdraw_amount"] = True
    
    method_name = "Telebirr" if method == "telebirr" else "CBE"
    
    await update.message.reply_text(
        f"💵 *Withdrawal Details*\n\n"
        f"📱 Method: {method_name}\n"
        f"📋 Account: {account_number}\n\n"
        f"*Enter withdrawal amount:*",
        parse_mode="Markdown"
    )

async def handle_withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdrawal amount input - Final step (Deduct immediately)"""
    if not context.user_data.get("awaiting_withdraw_amount"):
        return
    
    try:
        amount = float(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number")
        return
    
    # Check minimum withdrawal
    if amount < MIN_WITHDRAWAL:
        await update.message.reply_text(f"❌ Minimum withdrawal is {MIN_WITHDRAWAL} birr")
        return
    
    user = update.effective_user
    method = context.user_data.get("withdraw_method", "telebirr")
    account_number = context.user_data.get("withdraw_account", "")
    
    # Check balance
    cursor.execute(
        "SELECT balance FROM users WHERE user_id=?",
        (user.id,)
    )
    row = cursor.fetchone()
    
    if not row:
        await update.message.reply_text("❌ User not found")
        context.user_data["awaiting_withdraw_amount"] = False
        return
    
    balance = row[0]
    
    if amount > balance:
        await update.message.reply_text(f"❌ Insufficient balance. Available: {balance} birr")
        return
    
    # START TRANSACTION: Deduct balance IMMEDIATELY
    cursor.execute(
        "UPDATE users SET balance = balance - ? WHERE user_id=?",
        (amount, user.id)
    )
    
    # Save withdrawal request with deducted flag
    cursor.execute("""
        INSERT INTO transactions 
        (user_id, username, type, amount, method, status, account_number)
        VALUES (?, ?, 'withdraw', ?, ?, 'pending', ?)
    """, (user.id, user.username, amount, method, account_number))
    conn.commit()
    
    transaction_id = cursor.lastrowid
    
    # Calculate new balance
    new_balance = balance - amount
    
    # Notify admin with inline buttons
    method_name = "Telebirr" if method == "telebirr" else "CBE"
    
    admin_message = (
        f"📤 *NEW WITHDRAWAL REQUEST*\n\n"
        f"👤 User: @{user.username}\n"
        f"🆔 ID: `{user.id}`\n"
        f"💰 Amount: `{amount}` birr\n"
        f"📱 Method: {method_name}\n"
        f"📋 Account: `{account_number}`\n"
        f"📋 Transaction: #{transaction_id}\n"
        f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"💳 Balance Before: {balance} birr\n"
        f"💳 Balance After: {new_balance} birr\n\n"
        f"*Click buttons below to approve or reject:*"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ APPROVE", callback_data=f"approve_withdraw_{transaction_id}"),
            InlineKeyboardButton("❌ REJECT", callback_data=f"reject_withdraw_{transaction_id}")
        ]
    ]
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=admin_message,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        print(f"✅ Sent withdrawal notification to admin {ADMIN_USER_ID}")
    except Exception as e:
        print(f"❌ Error notifying admin: {e}")
        # Try alternative notification
        try:
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=f"📤 Withdrawal request from @{user.username} - Amount: {amount} - Transaction: #{transaction_id}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e2:
            print(f"❌ Failed to send even simple message: {e2}")
    
    # Clear context
    context.user_data["awaiting_withdraw_amount"] = False
    context.user_data["withdraw_method"] = None
    context.user_data["withdraw_account"] = None
    
    await update.message.reply_text(
        f"✅ *Withdrawal Request Submitted!*\n\n"
        f"📋 Transaction ID: #{transaction_id}\n"
        f"💰 Amount: {amount} birr\n"
        f"📱 Method: {method_name}\n"
        f"📋 Account: {account_number}\n"
        f"💳 Old Balance: {balance} birr\n"
        f"💳 New Balance: {new_balance} birr\n\n"
        "⏳ *Your withdrawal is being processed.*\n"
        "The amount has been deducted from your account.\n"
        "If approved, money will be sent to your account.\n"
        "If rejected, money will be returned to your balance.\n\n"
        "You will be notified when admin processes your request.",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )

# ======================
# ADMIN FUNCTIONS - UPDATED FOR IMMEDIATE DEDUCTION SYSTEM
# ======================
async def handle_admin_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin approval/rejection with refund system"""
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id != ADMIN_USER_ID:
        await query.edit_message_text("❌ Only admin can perform this action")
        return
    
    data = query.data.split("_")
    action = data[0]  # approve or reject
    transaction_type = data[1]  # deposit or withdraw
    transaction_id = int(data[2])
    
    # Get transaction details
    cursor.execute("""
        SELECT user_id, username, type, amount, method, account_number, status, image_filename
        FROM transactions 
        WHERE transaction_id=? AND status='pending'
    """, (transaction_id,))
    
    transaction = cursor.fetchone()
    
    if not transaction:
        await query.edit_message_text("❌ Transaction not found or already processed")
        return
    
    user_id, username, trans_type, amount, method, account_number, status, image_filename = transaction
    
    if action == "approve":
        if trans_type == "deposit":
            # Add balance to user
            cursor.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id=?", 
                (amount if amount else 0, user_id)
            )
            
            # Update transaction status
            cursor.execute("""
                UPDATE transactions 
                SET status='approved', processed_at=CURRENT_TIMESTAMP, processed_by=?
                WHERE transaction_id=?
            """, (update.effective_user.id, transaction_id))
            conn.commit()
            
            status = "approved"
            
            # Get current user balance for notification
            cursor.execute(
                "SELECT balance FROM users WHERE user_id=?",
                (user_id,)
            )
            current_balance_row = cursor.fetchone()
            current_balance = current_balance_row[0] if current_balance_row else 0
            
            user_message = f"✅ *Deposit Approved!*\n\n💰 {amount} has been added to your balance.\n💳 Current Balance: {current_balance} birr"
            
            # Delete the image file if it exists
            if image_filename:
                delete_transaction_image(image_filename)
        
        elif trans_type == "withdraw":
            # Just update status to approved (balance already deducted)
            cursor.execute("""
                UPDATE transactions 
                SET status='approved', processed_at=CURRENT_TIMESTAMP, processed_by=?
                WHERE transaction_id=?
            """, (update.effective_user.id, transaction_id))
            conn.commit()
            
            status = "approved"
            method_name = "Telebirr" if method == "telebirr" else "CBE"
            
            # Get current user balance for notification
            cursor.execute(
                "SELECT balance FROM users WHERE user_id=?",
                (user_id,)
            )
            current_balance_row = cursor.fetchone()
            current_balance = current_balance_row[0] if current_balance_row else 0
            
            # Notify user
            user_message = (
                f"✅ *Withdrawal Approved!*\n\n"
                f"📋 Transaction ID: #{transaction_id}\n"
                f"💰 Amount: {amount} birr\n"
                f"📱 Method: {method_name}\n"
                f"📋 Account: {account_number}\n"
                f"💳 Current Balance: {current_balance} birr\n\n"
                f"The amount has been sent to your {method_name} account.\n"
                f"It should arrive within 24 hours."
            )
            
            # Update admin message
            admin_update = (
                f"✅ *Withdrawal Approved*\n\n"
                f"Transaction #{transaction_id} has been approved.\n"
                f"💰 Amount: {amount} birr\n"
                f"👤 User: @{username}\n"
                f"📱 Method: {method_name}\n"
                f"📋 Account: {account_number}\n\n"
                f"✅ User notified. Money already deducted during request."
            )
    
    else:  # reject - REFUND THE MONEY
        status = "rejected"
        
        if trans_type == "withdraw":
            # REFUND: Add the amount back to user's balance
            cursor.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id=?",
                (amount, user_id)
            )
            
            # Get updated balance
            cursor.execute(
                "SELECT balance FROM users WHERE user_id=?",
                (user_id,)
            )
            updated_balance_row = cursor.fetchone()
            updated_balance = updated_balance_row[0] if updated_balance_row else 0
            
            # Update transaction status
            cursor.execute("""
                UPDATE transactions 
                SET status='rejected', processed_at=CURRENT_TIMESTAMP, processed_by=?
                WHERE transaction_id=?
            """, (update.effective_user.id, transaction_id))
            conn.commit()
            
            method_name = "Telebirr" if method == "telebirr" else "CBE"
            
            # Notify user (with refund information)
            user_message = (
                f"❌ *Withdrawal Rejected*\n\n"
                f"📋 Transaction ID: #{transaction_id}\n"
                f"💰 Amount: {amount} birr\n"
                f"📱 Method: {method_name}\n"
                f"💳 Refunded: ✅ YES\n"
                f"💳 Current Balance: {updated_balance} birr\n\n"
                f"Your withdrawal request was rejected by admin.\n"
                f"The amount has been returned to your balance.\n\n"
                f"Please contact support for more information."
            )
            
            # Update admin message
            admin_update = (
                f"❌ *Withdrawal Rejected (Refunded)*\n\n"
                f"Transaction #{transaction_id} has been rejected.\n"
                f"💰 Amount: {amount} birr REFUNDED\n"
                f"👤 User: @{username}\n"
                f"💳 Refunded Balance: {updated_balance} birr\n\n"
                f"User has been notified and amount refunded."
            )
        
        else:  # deposit rejection (no balance change needed)
            # Update transaction status
            cursor.execute("""
                UPDATE transactions 
                SET status='rejected', processed_at=CURRENT_TIMESTAMP, processed_by=?
                WHERE transaction_id=?
            """, (update.effective_user.id, transaction_id))
            conn.commit()
            
            # Delete the image file if it exists
            if image_filename:
                delete_transaction_image(image_filename)
            
            user_message = f"❌ *Deposit Rejected*\n\nYour deposit request (Transaction #{transaction_id}) was rejected by admin.\nPlease contact support for more information."
            admin_update = f"❌ *Deposit Rejected*\n\nTransaction #{transaction_id} has been rejected.\n👤 User: @{username}\n\nUser notified."
    
    # Notify user
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=user_message,
            parse_mode="Markdown"
        )
    except:
        pass  # User might have blocked the bot
    
    # Update admin message
    if trans_type == "deposit" and action == "approve":
        await query.edit_message_text(
            f"✅ *Deposit Approved*\n\n"
            f"Transaction #{transaction_id} has been approved.\n"
            f"💰 Amount: {amount} birr added to user balance.\n"
            f"👤 User: @{username}\n\n"
            f"User notified. Balance updated.",
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            admin_update,
            parse_mode="Markdown"
        )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel for managing transactions"""
    # Check if it's a callback or message
    if update.callback_query:
        user_id = update.callback_query.from_user.id
    else:
        user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        if update.callback_query:
            await update.callback_query.edit_message_text("❌ Access denied")
        else:
            await update.message.reply_text("❌ Access denied")
        return
    
    # Get pending transactions count
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE status='pending'")
    pending_count = cursor.fetchone()[0]
    
    # Get total users
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    # Get total balance in system
    cursor.execute("SELECT SUM(balance) FROM users")
    total_balance = cursor.fetchone()[0] or 0
    
    # Get today's stats
    cursor.execute("""
        SELECT 
            COUNT(*) as today_transactions,
            SUM(CASE WHEN status='approved' AND type='deposit' THEN amount ELSE 0 END) as today_deposits,
            SUM(CASE WHEN status='approved' AND type='withdraw' THEN amount ELSE 0 END) as today_withdrawals
        FROM transactions 
        WHERE DATE(created_at) = DATE('now')
    """)
    
    today_stats = cursor.fetchone()
    today_trans, today_deposits, today_withdrawals = today_stats or (0, 0, 0)
    
    text = (
        f"🛠 *ADMIN PANEL*\n\n"
        f"📊 *Overview*\n"
        f"• Pending Transactions: `{pending_count}`\n"
        f"• Total Users: `{total_users}`\n"
        f"• System Balance: `{total_balance}`\n\n"
        f"📈 *Today's Stats*\n"
        f"• Transactions: `{today_trans}`\n"
        f"• Deposits: `{today_deposits or 0}`\n"
        f"• Withdrawals: `{today_withdrawals or 0}`\n\n"
        f"*Click buttons below:*"
    )
    
    keyboard = [
        [InlineKeyboardButton("📋 View Transactions", callback_data="admin_transactions")],
        [InlineKeyboardButton("👥 View Users", callback_data="admin_users")],
        [InlineKeyboardButton("📊 View Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_refresh")]
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def admin_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show pending transactions with deduction status"""
    if update.effective_user.id != ADMIN_USER_ID:
        if update.callback_query:
            await update.callback_query.edit_message_text("❌ Access denied")
        else:
            await update.message.reply_text("❌ Access denied")
        return
    
    # Get chat_id from either message or callback_query
    if update.callback_query:
        chat_id = update.callback_query.message.chat_id
        # Edit the "Loading..." message
        await update.callback_query.edit_message_text("📋 Loading transactions...")
    else:
        chat_id = update.effective_chat.id
    
    # Get pending transactions
    cursor.execute("""
        SELECT transaction_id, type, user_id, username, amount, method, account_number, image_filename
        FROM transactions 
        WHERE status='pending'
        ORDER BY created_at DESC
    """)
    
    pending = cursor.fetchall()
    
    if not pending:
        text = "✅ *No pending transactions*"
        keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_home")]]
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return
    
    # Send transactions one by one with saved images
    sent_count = 0
    
    for trans in pending:
        trans_id, trans_type, user_id, username, amount, method, account, image_filename = trans
        
        # Get user's current balance for context
        cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
        user_balance_row = cursor.fetchone()
        user_balance = user_balance_row[0] if user_balance_row else 0
        
        trans_type_text = "📥 DEPOSIT" if trans_type == "deposit" else "📤 WITHDRAWAL"
        method_name = "Telebirr" if method == "telebirr" else "CBE"
        
        if trans_type == "deposit":
            text = (
                f"*{trans_type_text}*\n\n"
                f"👤 User: @{username or 'N/A'}\n"
                f"🆔 ID: `{user_id}`\n"
                f"💰 Amount: `{amount}`\n"
                f"📱 Method: {method_name}\n"
                f"📋 Transaction: #{trans_id}\n"
                f"💳 User Balance: `{user_balance}`\n\n"
                f"*Actions:*"
            )
        else:  # withdrawal
            # For withdrawals, note that balance is already deducted
            text = (
                f"*{trans_type_text}*\n\n"
                f"⚠️ *Balance already deducted*\n\n"
                f"👤 User: @{username or 'N/A'}\n"
                f"🆔 ID: `{user_id}`\n"
                f"💰 Amount: `{amount}`\n"
                f"📱 Method: {method_name}\n"
                f"📋 Account: `{account}`\n"
                f"📋 Transaction: #{trans_id}\n"
                f"💳 User Balance: `{user_balance}`\n\n"
                f"*Actions:*"
            )
        
        keyboard = [
            [
                InlineKeyboardButton(f"✅ Approve #{trans_id}", callback_data=f"approve_{trans_type}_{trans_id}"),
                InlineKeyboardButton(f"❌ Reject #{trans_id}", callback_data=f"reject_{trans_type}_{trans_id}")
            ]
        ]
        
        try:
            if trans_type == "deposit" and image_filename:
                # Send the saved image file
                image_file = get_image_file(image_filename)
                if image_file:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=image_file,
                        caption=text,
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    image_file.close()
                    sent_count += 1
                else:
                    # Send message without image
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"{text}\n\n⚠️ *Note:* Screenshot file not found on server.",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    sent_count += 1
            else:
                # Send regular message for withdrawals
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                sent_count += 1
        except Exception as e:
            print(f"Error sending transaction {trans_id}: {e}")
            # Try without photo
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"{text}\n\n⚠️ Error loading transaction details.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                sent_count += 1
            except Exception as e2:
                print(f"Error sending fallback message: {e2}")
    
    # Send summary message
    summary_text = f"📋 *Sent {sent_count} pending transactions for review*\n\nUse the buttons above to approve or reject each transaction."
    
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_transactions")],
        [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_home")]
    ]
    
    if update.callback_query:
        # Edit the loading message to show summary
        await update.callback_query.edit_message_text(
            summary_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            summary_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed stats"""
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Access denied")
        return
    
    # Get overall stats
    cursor.execute("""
        SELECT 
            COUNT(*) as total_transactions,
            SUM(CASE WHEN type='deposit' THEN amount ELSE 0 END) as total_deposits,
            SUM(CASE WHEN type='withdraw' THEN amount ELSE 0 END) as total_withdrawals,
            SUM(CASE WHEN status='approved' AND type='deposit' THEN amount ELSE 0 END) as approved_deposits,
            SUM(CASE WHEN status='approved' AND type='withdraw' THEN amount ELSE 0 END) as approved_withdrawals,
            SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending_count
        FROM transactions
    """)
    
    stats = cursor.fetchone()
    
    if stats:
        total_trans, total_deposits, total_withdrawals, approved_deposits, approved_withdrawals, pending_count = stats
        
        # Get user stats
        cursor.execute("SELECT COUNT(*), SUM(balance) FROM users")
        user_count, total_balance = cursor.fetchone()
        
        text = (
            f"📊 *SYSTEM STATISTICS*\n\n"
            f"👥 *User Stats*\n"
            f"• Total Users: `{user_count}`\n"
            f"• Total Balance in System: `{total_balance or 0}`\n\n"
            f"💰 *Financial Overview*\n"
            f"• Total Deposits: `{approved_deposits or 0}`\n"
            f"• Total Withdrawals: `{approved_withdrawals or 0}`\n"
            f"• Net Flow: `{(approved_deposits or 0) - (approved_withdrawals or 0)}`\n\n"
            f"📋 *Transaction Stats*\n"
            f"• Total Transactions: `{total_trans}`\n"
            f"• Pending: `{pending_count}`\n"
            f"• Approved: `{total_trans - pending_count}`\n\n"
        )
        
        # Get today's activity
        cursor.execute("""
            SELECT 
                COUNT(*) as today_count,
                SUM(CASE WHEN type='deposit' AND status='approved' THEN amount ELSE 0 END) as today_deposits,
                SUM(CASE WHEN type='withdraw' AND status='approved' THEN amount ELSE 0 END) as today_withdrawals
            FROM transactions 
            WHERE DATE(created_at) = DATE('now')
        """)
        
        today = cursor.fetchone()
        if today:
            today_count, today_deposits, today_withdrawals = today
            text += f"📅 *Today's Activity*\n"
            text += f"• Transactions: `{today_count or 0}`\n"
            text += f"• Deposits: `{today_deposits or 0}`\n"
            text += f"• Withdrawals: `{today_withdrawals or 0}`\n"
    
    keyboard = [
        [InlineKeyboardButton("📋 View Transactions", callback_data="admin_transactions")],
        [InlineKeyboardButton("👥 View Users", callback_data="admin_users")],
        [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_home")]
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def admin_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all user balances (admin only)"""
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Access denied")
        return
    
    cursor.execute("""
        SELECT user_id, username, balance
        FROM users
        ORDER BY balance DESC
        LIMIT 20
    """)
    
    users = cursor.fetchall()
    
    text = "👥 *USER BALANCES*\n\n"
    total_balance = 0
    
    for user_id, username, balance in users:
        text += f"👤 @{username or 'No username'}\n"
        text += f"   🆔: `{user_id}`\n"
        text += f"   💰: `{balance}`\n\n"
        total_balance += balance
    
    text += f"📊 *Total Balance:* `{total_balance}`"
    
    keyboard = [
        [InlineKeyboardButton("📋 View Transactions", callback_data="admin_transactions")],
        [InlineKeyboardButton("📊 View Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_home")]
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin panel callbacks"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_USER_ID:
        await query.edit_message_text("❌ Access denied")
        return
    
    data = query.data
    
    print(f"DEBUG: Admin callback data: {data}")
    
    try:
        if data == "admin_home":
            await admin_panel(update, context)
        elif data == "admin_transactions":
            # We'll handle it in the admin_transactions function
            await admin_transactions(update, context)
        elif data == "admin_users":
            await admin_balance(update, context)
        elif data == "admin_stats":
            await admin_stats_command(update, context)
        elif data == "admin_refresh":
            await admin_panel(update, context)
    except Exception as e:
        print(f"Error in admin_callback_handler: {e}")
        await query.edit_message_text(f"❌ Error: {str(e)}")

async def check_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check if bot can message admin"""
    user_id = update.effective_user.id
    
    if user_id == ADMIN_USER_ID:
        try:
            # Test if bot can send message to admin
            test_message = await update.message.reply_text(
                f"✅ You are admin!\n"
                f"👤 Your ID: {user_id}\n"
                f"🤖 Bot can message you: YES\n\n"
                f"Commands:\n"
                f"/admin - Admin panel\n"
                f"/transactions - View pending transactions\n"
                f"/users - View user balances\n"
                f"/stats - Detailed statistics",
                parse_mode="Markdown"
            )
            
            # Also try to send a test notification
            admin_test_msg = "🔔 *Test Notification*\n\nThis is a test message to verify the bot can send notifications to admin."
            test_keyboard = [[InlineKeyboardButton("✅ Test Button", callback_data="test_button")]]
            
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=admin_test_msg,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(test_keyboard)
            )
            
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
    else:
        await update.message.reply_text("❌ You are not admin")

async def admin_cleanup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clean up old transaction images"""
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Access denied")
        return
    
    # Count files before cleanup
    ensure_image_directory()
    files_before = len(os.listdir("transaction_images"))
    
    # Clean up processed transaction images
    cursor.execute("""
        SELECT image_filename 
        FROM transactions 
        WHERE status != 'pending' 
        AND image_filename IS NOT NULL
    """)
    processed_images = cursor.fetchall()
    
    deleted_count = 0
    for (filename,) in processed_images:
        if delete_transaction_image(filename):
            deleted_count += 1
    # Count files after cleanup
    files_after = len(os.listdir("transaction_images"))
    
    await update.message.reply_text(
        f"🧹 *Image Cleanup Complete*\n\n"
        f"• Deleted files: `{deleted_count}`\n"
        f"• Files before: `{files_before}`\n"
        f"• Files after: `{files_after}`\n"
        f"• Space freed: Approx {deleted_count * 0.5:.1f} MB (est.)",
        parse_mode="Markdown"
    )

# ======================
# TRANSACTION STATUS CHECK
# ======================
async def check_transaction_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Let users check their transaction status"""
    user = update.effective_user
    
    # Get pending transactions for this user
    cursor.execute("""
        SELECT transaction_id, type, amount, method, status, created_at
        FROM transactions 
        WHERE user_id=? AND status IN ('pending', 'approved', 'rejected')
        ORDER BY transaction_id DESC
        LIMIT 5
    """, (user.id,))
    
    transactions = cursor.fetchall()
    
    if not transactions:
        await update.message.reply_text(
            "📋 *No transactions found*\n\n"
            "You don't have any transactions yet.",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    text = "📋 *YOUR TRANSACTIONS*\n\n"
    
    for trans_id, trans_type, amount, method, status, created_at in transactions:
        status_emoji = {
            "pending": "⏳",
            "approved": "✅",
            "rejected": "❌"
        }.get(status, "📝")
        
        method_name = "Telebirr" if method == "telebirr" else "CBE"
        
        text += f"{status_emoji} *Transaction #{trans_id}*\n"
        text += f"   Type: {trans_type.upper()}\n"
        text += f"   Amount: {amount} birr\n"
        text += f"   Method: {method_name}\n"
        text += f"   Status: {status}\n"
        text += f"   Date: {created_at}\n\n"
    
    text += "ℹ️ *Note:* For withdrawals, amount is deducted immediately when submitted.\n"
    text += "If rejected, it will be refunded to your balance."
    
    keyboard = [
        [InlineKeyboardButton("?? Check Balance", callback_data="menu_balance")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
    ]
    
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ======================
# NEW: RESULTS COMMAND
# ======================
async def results_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent match results from database"""
    # Determine if this is from a callback or message
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        user = query.from_user
        is_callback = True
    else:
        user = update.effective_user
        is_callback = False
    
    # Get recent results from database
    recent_results = results_db.get_all_results(limit=15)
    
    if not recent_results:
        if is_callback:
            await query.edit_message_text(
                "📊 *No Match Results Available*\n\n"
                "No results have been recorded yet. Results are automatically saved when matches finish.",
                parse_mode="Markdown",
                reply_markup=get_main_menu_keyboard()
            )
        else:
            await update.message.reply_text(
                "📊 *No Match Results Available*\n\n"
                "No results have been recorded yet. Results are automatically saved when matches finish.",
                parse_mode="Markdown",
                reply_markup=get_main_menu_keyboard()
            )
        return
    
    text = "📊 *RECENT MATCH RESULTS*\n\n"
    
    for result in recent_results:
        home = result['home_team'] or "Home"
        away = result['away_team'] or "Away"
        score = f"{result['home_goals']}-{result['away_goals']}"
        status = result['status']
        
        text += f"⚽ *{home}* {score} *{away}*\n"
        
        if result['league_name']:
            text += f"   🏆 {result['league_name']}\n"
        
        text += f"   📅 {result['match_date']} | 📋 Status: {status}\n\n"
    
    # Add database stats
    stats = results_db.get_stats()
    text += f"📈 *Database Stats:* {stats['total_results']} results stored\n"
    text += "🗑️ *Note:* Results are automatically deleted after 2 days\n\n"
    text += "To check your bet status, use /mybets"
    
    keyboard = [
        [InlineKeyboardButton("📊 My Bets", callback_data="menu_mybets")],
        [InlineKeyboardButton("🎫 Bet Slip", callback_data="menu_betslip")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
    ]
    
    if is_callback:
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ======================
# INLINE BET SLIP - UPDATED FOR OVER/UNDER
# ======================
async def show_betslip_inline(query):
    user_id = query.from_user.id
    slip = get_betslip(user_id)

    if not slip:
        keyboard = [
            [InlineKeyboardButton("🏆 Browse Leagues", callback_data="menu_leagues_today")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
        ]
        await query.edit_message_text(
            "🎫 *Your Bet Slip is Empty*\n\nAdd selections from available matches!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    text = "🎫 *YOUR BET SLIP*\n"
    text += "─" * 30 + "\n\n"
    
    total_odds = 1.0
    keyboard = []
    
    for i, s in enumerate(slip, 1):
        # Get match details
        cursor.execute("""
            SELECT t1.name as home, t2.name as away, l.name as league_name
            FROM fixtures f
            JOIN teams t1 ON f.home_team_id = t1.team_id
            JOIN teams t2 ON f.away_team_id = t2.team_id
            JOIN leagues l ON f.league_id = l.league_id
            WHERE f.fixture_id=?
        """, (s["fixture_id"],))
        
        match = cursor.fetchone()
        match_text = f"Match {s['fixture_id']}"
        if match:
            home, away, league_name = match
            if s["market"] == "1X2":
                pick_text = {
                    "1": f"{home} Win",
                    "X": "Draw",
                    "2": f"{away} Win"
                }.get(s["pick"], s["pick"])
            else:  # OU market
                pick_text = s["pick"]
            
            match_text = f"{home} vs {away} ({league_name})"
            
            # Add remove button for each selection
            keyboard.append([
                InlineKeyboardButton(
                    f"❌ Remove {home[:5]} vs {away[:5]}",
                    callback_data=f"remove_{s['fixture_id']}"
                )
            ])
        else:
            pick_text = s["pick"]
            keyboard.append([
                InlineKeyboardButton(
                    f"❌ Remove Selection {i}",
                    callback_data=f"remove_{s['fixture_id']}"
                )
            ])
        
        # Add market type to display
        market_display = "1X2" if s["market"] == "1X2" else "O/U"
        
        text += f"*{i}. {match_text}*\n"
        text += f"   📊 {pick_text}\n"
        text += f"   🎯 Market: {market_display}\n"
        text += f"   📈 Odds: {s['odds']}\n\n"
        
        total_odds *= float(s["odds"])

    total_odds = round(total_odds, 2)
    text += "─" * 30 + "\n"
    text += f"*Total Odds:* `{total_odds}`\n\n"
    text += "To place bet, click Place Bet button:"

    # Add action buttons
    keyboard.append([InlineKeyboardButton("💵 Place Bet (Enter Stake)", callback_data="enter_stake")])
    keyboard.append([InlineKeyboardButton("🗑 Clear Entire Bet Slip", callback_data="clear_betslip")])
    keyboard.append([InlineKeyboardButton("🏆 Add More Matches", callback_data="menu_leagues_today")])
    keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")])

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ======================
# ADD TO BET SLIP - UPDATED FOR MULTIPLE OVER/UNDER LINES
# ======================
async def bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Format: bet_{fixture_id}_{market}_{pick}_{odds}
    try:
        data_parts = query.data.split("_")
        _, fixture_id, market, pick, odds = data_parts[:5]
        fixture_id = int(data_parts[1])
        odds = float(odds)
        
        # Reconstruct pick for Over/Under (it might have spaces)
        if market == "OU" and len(data_parts) > 5:
            pick = f"{pick} {data_parts[4]}"
            odds = float(data_parts[5])
    except ValueError as e:
        print(f"Error parsing callback data: {e}, data: {query.data}")
        await query.edit_message_text("❌ Error processing bet button. Please refresh matches.")
        return

    user_id = query.from_user.id
    
    # Get match details for confirmation message
    cursor.execute("""
        SELECT t1.name as home, t2.name as away, l.name as league_name
        FROM fixtures f
        JOIN teams t1 ON f.home_team_id = t1.team_id
        JOIN teams t2 ON f.away_team_id = t2.team_id
        JOIN leagues l ON f.league_id = l.league_id
        WHERE f.fixture_id = ?
    """, (fixture_id,))
    
    match = cursor.fetchone()
    if match:
        home, away, league_name = match
        if market == "1X2":
            pick_text = {
                "1": f"{home} Win",
                "X": "Draw",
                "2": f"{away} Win"
            }.get(pick, pick)
        else:  # OU market
            pick_text = pick  # Will display "Over 1.5", "Under 2.5", etc.
        
        match_text = f"{home} vs {away} ({league_name})"
    else:
        match_text = f"Fixture {fixture_id}"
        pick_text = pick

    success, msg = add_selection(
        user_id,
        fixture_id,
        market,
        pick,
        odds
    )

    keyboard = [
        [InlineKeyboardButton("🎫 View Bet Slip", callback_data="menu_betslip")],
        [InlineKeyboardButton("🏆 Browse More Leagues", callback_data="menu_leagues_today")],
        [InlineKeyboardButton("🔙 Back to This Match", callback_data=f"match_{fixture_id}")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
    ]

    await query.edit_message_text(
        f"🎯 *Selection Added*\n\n{match_text}\n📊 Prediction: *{pick_text}*\n💰 Odds: *{odds:.2f}*\n\n{msg}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ======================
# REMOVE SELECTION FROM BET SLIP
# ======================
async def remove_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("_")
    if len(data) == 3 and data[0] == "remove":
        fixture_id = int(data[1])
        user_id = query.from_user.id
        
        # Remove selection
        success, msg = remove_selection(user_id, fixture_id)
        
        if success:
            await show_betslip_inline(query)
        else:
            keyboard = [
                [InlineKeyboardButton("🎫 Back to Bet Slip", callback_data="menu_betslip")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
            ]
            await query.edit_message_text(
                msg,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

# ======================
# BET SLIP ACTIONS
# ======================
async def betslip_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == "clear_betslip":
        clear_betslip(user_id)
        keyboard = [
            [InlineKeyboardButton("🏆 Browse Leagues", callback_data="menu_leagues_today")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
        ]
        await query.edit_message_text(
            "✅ *Bet Slip Cleared!*\n\nAll selections have been removed.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif query.data == "enter_stake":
        # Mark that we're awaiting stake
        context.user_data["awaiting_stake"] = True
        
        keyboard = [
            [InlineKeyboardButton("❌ Cancel", callback_data="menu_betslip")]
        ]
        
        await query.edit_message_text(
            "💰 *Enter Stake Amount*\n\nPlease send me the amount you want to bet:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ======================
# INLINE BALANCE
# ======================
async def show_balance_inline(query):
    user_id = query.from_user.id
    cursor.execute(
        "SELECT balance FROM users WHERE user_id=?",
        (user_id,)
    )
    row = cursor.fetchone()
    
    if row:
        balance = row[0]
        
        # Get pending bets count
        cursor.execute(
            "SELECT COUNT(*) FROM bets WHERE user_id=? AND status='PENDING'",
            (user_id,)
        )
        pending_bets = cursor.fetchone()[0]
        
        # Get won/lost stats
        cursor.execute(
            "SELECT COUNT(*) FROM bets WHERE user_id=? AND status='WON'",
            (user_id,)
        )
        won_bets = cursor.fetchone()[0]
        
        cursor.execute(
            "SELECT COUNT(*) FROM bets WHERE user_id=? AND status='LOST'",
            (user_id,)
        )
        lost_bets = cursor.fetchone()[0]
        
        text = f"💰 *YOUR BALANCE*\n"
        text += "─" * 30 + "\n\n"
        text += f"💵 *Available:* `{balance}`\n\n"
        text += f"📊 *Stats*\n"
        text += f"✅ Won: `{won_bets}`\n"
        text += f"❌ Lost: `{lost_bets}`\n"
        text += f"⏳ Pending: `{pending_bets}`\n"
    else:
        text = "❌ User not found"

    keyboard = [
        [
            InlineKeyboardButton("📥 Deposit", callback_data="menu_deposit"),
            InlineKeyboardButton("📤 Withdraw", callback_data="menu_withdraw")
        ],
        [InlineKeyboardButton("🎫 My Bet Slip", callback_data="menu_betslip")],
        [InlineKeyboardButton("📊 My Bets", callback_data="menu_mybets")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
    ]

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ======================
# INLINE MY BETS - ENHANCED WITH DETAILED SELECTIONS
# ======================
async def show_my_bets_inline(query):
    user_id = query.from_user.id
    
    cursor.execute("""
        SELECT bet_id, selections, total_odds, stake, status, payout, created_at
        FROM bets 
        WHERE user_id=? 
        ORDER BY bet_id DESC 
        LIMIT 5
    """, (user_id,))
    
    bets = cursor.fetchall()
    
    if not bets:
        keyboard = [
            [InlineKeyboardButton("🏆 Place a Bet", callback_data="menu_leagues_today")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
        ]
        await query.edit_message_text(
            "📊 *No Bets Yet*\n\nPlace your first bet from the leagues!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    text = "📊 *YOUR BET HISTORY*\n"
    text += "─" * 30 + "\n\n"
    
    for bet_id, selections_json, total_odds, stake, status, payout, created_at in bets:
        status_emoji = {
            "PENDING": "⏳",
            "WON": "✅",
            "LOST": "❌"
        }.get(status, "📝")
        
        text += f"{status_emoji} *Bet #{bet_id}* - {status}\n"
        text += f"   📅 Date: `{created_at[:16]}`\n"
        text += f"   📈 Total Odds: `{total_odds}`\n"
        text += f"   💵 Stake: `{stake}` birr\n"
        text += f"   🏆 Potential Win: `{payout}` birr\n"
        
        try:
            selections_data = json.loads(selections_json)
            
            text += f"   \n   📋 *Selections:*\n"
            
            for i, s in enumerate(selections_data, 1):
                cursor.execute("""
                    SELECT t1.name as home, t2.name as away, l.name as league_name
                    FROM fixtures f
                    JOIN teams t1 ON f.home_team_id = t1.team_id
                    JOIN teams t2 ON f.away_team_id = t2.team_id
                    JOIN leagues l ON f.league_id = l.league_id
                    WHERE f.fixture_id=?
                """, (s["fixture_id"],))
                match = cursor.fetchone()
                
                if match:
                    home, away, league_name = match
                    
                    # Determine market and pick display
                    market = s.get("market", "1X2")
                    pick = s["pick"]
                    odds = s["odds"]
                    
                    if market == "1X2":
                        pick_display = {
                            "1": f"{home} Win",
                            "X": "Draw",
                            "2": f"{away} Win"
                        }.get(pick, f"Unknown ({pick})")
                        market_display = "1X2"
                    else:  # OU market
                        pick_display = pick  # "Over 1.5", "Under 2.5", etc.
                        market_display = "O/U"
                    
                    text += f"      {i}. *{home}* vs *{away}*\n"
                    text += f"         🎯 Pick: `{pick_display}`\n"
                    text += f"         📊 Market: `{market_display}`\n"
                    text += f"         📈 Odds: `{odds}`\n"
                    
                    # Add league info if available
                    if league_name:
                        text += f"         🏆 League: `{league_name[:20]}`\n"
                    
                    text += f"         \n"  # Spacing between selections
                else:
                    text += f"      {i}. Match ID: `{s['fixture_id']}`\n"
                    text += f"         Pick: `{s.get('pick', 'N/A')}`\n"
                    text += f"         Odds: `{s.get('odds', 'N/A')}`\n"
                    text += f"         \n"
            
            # Remove extra newline at the end
            if text.endswith("\n         \n"):
                text = text[:-11]
            
        except Exception as e:
            print(f"Error parsing selections for bet #{bet_id}: {e}")
            text += f"   📋 Selections: Error loading bet details\n"
        
        text += "\n"  # Spacing between bets
    # Add summary
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN status='WON' THEN payout ELSE 0 END) as total_won,
            SUM(CASE WHEN status='LOST' THEN stake ELSE 0 END) as total_lost,
            COUNT(*) as total_bets,
            SUM(CASE WHEN status='PENDING' THEN 1 ELSE 0 END) as pending_bets,
            SUM(CASE WHEN status='WON' THEN 1 ELSE 0 END) as won_bets,
            SUM(CASE WHEN status='LOST' THEN 1 ELSE 0 END) as lost_bets
        FROM bets WHERE user_id=?
    """, (user_id,))
    
    summary = cursor.fetchone()
    if summary and summary[2] > 0:
        total_won, total_lost, total_bets, pending_bets, won_bets, lost_bets = summary
        text += "─" * 30 + "\n"
        text += f"📈 *Betting Summary*\n\n"
        text += f"📊 *Statistics:*\n"
        text += f"• Total Bets: `{total_bets}`\n"
        text += f"• Won: `{won_bets or 0}`\n"
        text += f"• Lost: `{lost_bets or 0}`\n"
        text += f"• Pending: `{pending_bets or 0}`\n"
        text += f"• Win Rate: `{((won_bets or 0) / total_bets * 100):.1f}%`\n\n"
        text += f"💰 *Financial Summary:*\n"
        text += f"• Total Won: `{total_won or 0}` birr\n"
        text += f"• Total Lost: `{total_lost or 0}` birr\n"
        text += f"• Net Profit/Loss: `{(total_won or 0) - (total_lost or 0)}` birr\n"

    keyboard = [
        [InlineKeyboardButton("🎫 Current Bet Slip", callback_data="menu_betslip")],
        [InlineKeyboardButton("💰 My Balance", callback_data="menu_balance")],
        [InlineKeyboardButton("🔍 View Older Bets", callback_data="view_older_bets")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
    ]

    # Check if message is too long (Telegram has 4096 character limit)
    if len(text) > 4000:
        text = text[:4000] + "\n\n... (message too long, showing partial history)"

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ======================
# VIEW OLDER BETS HANDLER
# ======================
async def view_older_bets_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle viewing older bets with pagination"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    page = context.user_data.get("bet_page", 1)
    
    # Calculate offset for pagination
    offset = (page - 1) * 5
    
    cursor.execute("""
        SELECT bet_id, selections, total_odds, stake, status, payout, created_at
        FROM bets 
        WHERE user_id=? 
        ORDER BY bet_id DESC 
        LIMIT 5 OFFSET ?
    """, (user_id, offset))
    
    bets = cursor.fetchall()
    
    if not bets:
        if page == 1:
            await query.edit_message_text(
                "📊 *No Bets Found*\n\nYou haven't placed any bets yet!",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏆 Place a Bet", callback_data="menu_leagues_today")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
                ])
            )
        else:
            await query.edit_message_text(
                "📊 *No More Bets*\n\nYou've reached the end of your bet history!",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back to Recent Bets", callback_data="menu_mybets")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
                ])
            )
        return
    
    text = f"📊 *YOUR BET HISTORY (Page {page})*\n"
    text += "─" * 30 + "\n\n"
    
    for bet_id, selections_json, total_odds, stake, status, payout, created_at in bets:
        status_emoji = {
            "PENDING": "⏳",
            "WON": "✅",
            "LOST": "❌"
        }.get(status, "📝")
        
        text += f"{status_emoji} *Bet #{bet_id}*\n"
        text += f"   📅 Date: `{created_at[:16]}`\n"
        text += f"   📊 Status: `{status}`\n"
        text += f"   📈 Total Odds: `{total_odds}`\n"
        text += f"   💵 Stake: `{stake}` birr\n"
        text += f"   🏆 Potential/Won: `{payout}` birr\n"
        
        # Show first selection as example
        try:
            selections_data = json.loads(selections_json)
            if selections_data:
                s = selections_data[0]
                cursor.execute("""
                    SELECT t1.name as home, t2.name as away
                    FROM fixtures f
                    JOIN teams t1 ON f.home_team_id = t1.team_id
                    JOIN teams t2 ON f.away_team_id = t2.team_id
                    WHERE f.fixture_id=?
                """, (s["fixture_id"],))
                match = cursor.fetchone()
                
                if match:
                    home, away = match
                    market = s.get("market", "1X2")
                    pick = s["pick"]
                    
                    if market == "1X2":
                        pick_display = {
                            "1": f"{home} Win",
                            "X": "Draw",
                            "2": f"{away} Win"
                        }.get(pick, pick)
                    else:
                        pick_display = pick
                    
                    text += f"   📋 Example Pick: `{pick_display}`\n"
                
                # Show number of selections
                text += f"   🔢 Selections: `{len(selections_data)}` matches\n"
        except:
            pass
        
        text += "\n"
    
    # Count total bets for pagination
    cursor.execute("SELECT COUNT(*) FROM bets WHERE user_id=?", (user_id,))
    total_bets = cursor.fetchone()[0]
    
    # Calculate if there are more pages
    total_pages = (total_bets + 4) // 5  # Ceiling division
    
    keyboard_buttons = []
    
    # Pagination buttons
    if page > 1:
        keyboard_buttons.append(InlineKeyboardButton("◀️ Previous", callback_data=f"bet_page_{page-1}"))
    if offset + 5 < total_bets:
        keyboard_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"bet_page_{page+1}"))
    
    if keyboard_buttons:
        keyboard = [keyboard_buttons]
    
    # Add navigation buttons
    keyboard.append([InlineKeyboardButton("📋 View Full Recent Bets", callback_data="menu_mybets")])
    keyboard.append([InlineKeyboardButton("💰 My Balance", callback_data="menu_balance")])
    keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")])
    
    text += f"📄 *Page {page} of {total_pages}* • *Total Bets: {total_bets}*"
    
    # Store current page in context
    context.user_data["bet_page"] = page
    
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ======================
# BET PAGE PAGINATION HANDLER
# ======================
async def bet_page_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pagination for bet history"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("_")
    if len(data) == 3 and data[0] == "bet" and data[1] == "page":
        page = int(data[2])
        context.user_data["bet_page"] = page
        await view_older_bets_handler(update, context)


# ======================
# STAKE INPUT HANDLER
# ======================
async def stake_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not context.user_data.get("awaiting_stake"):
        # If not awaiting stake, show main menu
        await show_main_menu(update, context)
        return

    try:
        stake = float(update.message.text)
    except ValueError:
        await update.message.reply_text(
            "❌ Please enter a valid number for stake.",
            reply_markup=get_main_menu_keyboard()
        )
        return

    # Place the bet
    success, msg = place_bet(user_id, stake)
    
    # Clear the awaiting stake flag
    context.user_data["awaiting_stake"] = False
    
    if success:
        keyboard = [
            [InlineKeyboardButton("🏆 Browse More Leagues", callback_data="menu_leagues_today")],
            [InlineKeyboardButton("📊 View My Bets", callback_data="menu_mybets")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
        ]
        await update.message.reply_text(
            f"✅ *Bet Placed Successfully!*\n\n{msg}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        keyboard = [
            [InlineKeyboardButton("🎫 View Bet Slip", callback_data="menu_betslip")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
        ]
        await update.message.reply_text(
            f"❌ *Bet Failed*\n\n{msg}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ======================
# MESSAGE HANDLER - UPDATED WITH SEARCH FUNCTIONALITY
# ======================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages"""
    
    # Check if awaiting team search
    if context.user_data.get("awaiting_team_search"):
        await search_team_handler(update, context)
        return
    
    # Check if awaiting stake (existing functionality)
    if context.user_data.get("awaiting_stake"):
        await stake_handler(update, context)
        return
    
    # Check if awaiting withdrawal amount
    if context.user_data.get("awaiting_withdraw_amount"):
        await handle_withdraw_amount(update, context)
        return
    
    # Check if awaiting withdrawal account number
    if context.user_data.get("awaiting_withdraw_account"):
        await handle_withdraw_account(update, context)
        return
    
    # Check if awaiting deposit amount
    if context.user_data.get("awaiting_deposit_amount"):
        await handle_deposit_amount(update, context)
        return
    
    # If no specific state, show main menu
    await show_main_menu(update, context)

# ======================
# PHOTO HANDLER
# ======================
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages (deposit screenshots)"""
    if context.user_data.get("awaiting_deposit_screenshot"):
        await handle_deposit_screenshot(update, context)
    else:
        await update.message.reply_text(
            "Please use the deposit menu to send screenshots.",
            reply_markup=get_main_menu_keyboard()
        )

# ======================
# TEST BUTTON HANDLER
# ======================
async def test_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "test_button":
        await query.edit_message_text("✅ Test button works! Admin notifications are functional.")

# ======================
# DEBUG MATCH TIME COMMAND
# ======================
async def debug_match_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Debug command to check match time status"""
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Admin only")
        return
    
    cursor.execute("""
        SELECT fixture_id, home_team_id, away_team_id, start_time, status,
               datetime(start_time) as start_dt,
               datetime('now') as now_dt,
               (julianday('now') - julianday(start_time)) * 1440 as minutes_diff
        FROM fixtures
        WHERE status = 'NS'
        ORDER BY start_time
        LIMIT 10
    """)
    
    matches = cursor.fetchall()
    
    text = "🕒 *Match Time Debug*\n\n"
    
    for match in matches:
        fixture_id, home_id, away_id, start_time, status, start_dt, now_dt, minutes_diff = match
        
        # Get team names
        cursor.execute("SELECT name FROM teams WHERE team_id = ?", (home_id,))
        home_name = cursor.fetchone()[0] if cursor.fetchone() else f"Team {home_id}"
        
        cursor.execute("SELECT name FROM teams WHERE team_id = ?", (away_id,))
        away_name = cursor.fetchone()[0] if cursor.fetchone() else f"Team {away_id}"
        
        overdue = float(minutes_diff) > MATCH_GRACE_PERIOD_MINUTES if minutes_diff else False
        
        text += f"⚽ *{home_name} vs {away_name}*\n"
        text += f"   🆔: {fixture_id}\n"
        text += f"   ⏰: {start_time}\n"
        text += f"   📊: {status}\n"
        text += f"   ⏳: {minutes_diff:.1f} minutes {'❌ OVERDUE' if overdue else '✅ OK'}\n\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")

# ======================
# COMMAND HANDLERS - UPDATED FOR LEAGUE-FIRST NAVIGATION
# ======================
async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await show_balance_inline(update.callback_query)
    else:
        # Create a fake query object for message
        class FakeQuery:
            def __init__(self, update):
                self.message = update.message
                self.from_user = update.effective_user
                self.data = "menu_balance"
            
            async def answer(self):
                pass
            
            async def edit_message_text(self, text, parse_mode=None, reply_markup=None):
                await self.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        
        fake_query = FakeQuery(update)
        await show_balance_inline(fake_query)

async def leagues_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler for showing today's leagues"""
    await show_leagues_menu(update, context, day_offset=0, page=0)

async def betslip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await show_betslip_inline(update.callback_query)
    else:
        # Create a fake query object for message
        class FakeQuery:
            def __init__(self, update):
                self.message = update.message
                self.from_user = update.effective_user
                self.data = "menu_betslip"
            
            async def answer(self):
                pass
            
            async def edit_message_text(self, text, parse_mode=None, reply_markup=None):
                await self.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        
        fake_query = FakeQuery(update)
        await show_betslip_inline(fake_query)

async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await show_deposit_methods(update.callback_query, context)
    else:
        # Create a fake query object for message
        class FakeQuery:
            def __init__(self, update):
                self.message = update.message
                self.from_user = update.effective_user
                self.data = "menu_deposit"
            
            async def answer(self):
                pass
            
            async def edit_message_text(self, text, parse_mode=None, reply_markup=None):
                await self.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        
        fake_query = FakeQuery(update)
        await show_deposit_methods(fake_query, context)

async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_withdraw(update, context)

# ======================
# REFRESH ODDS HANDLER - FIXED VERSION
# ======================
async def refresh_odds_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle refresh odds button"""
    query = update.callback_query
    await query.answer()
    
    # Extract fixture_id from callback data: refresh_odds_{fixture_id}
    try:
        data_parts = query.data.split("_")
        if len(data_parts) >= 3:
            fixture_id = int(data_parts[2])
        else:
            print(f"Error: Invalid callback data format: {query.data}")
            await query.edit_message_text("❌ Error refreshing odds. Please try again.")
            return
        
        # Clear cache for this fixture
        cache.delete(f"odds_{fixture_id}")
        print(f"Cache cleared for fixture {fixture_id}")
        
        # Call match_details_with_odds to refresh with force refresh
        await match_details_with_odds(update, context, fixture_id=fixture_id)
    except ValueError as e:
        print(f"Error parsing fixture_id from {query.data}: {e}")
        await query.edit_message_text("❌ Error: Could not refresh odds. Please select the match again.")

# ======================
# LEAGUE INFO HANDLER
# ======================
async def league_info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed league information"""
    query = update.callback_query
    await query.answer()
    
    # Extract league_id from callback data: league_info_{league_id}
    league_id = int(query.data.split("_")[2])
    
    # Get league info
    league_info = get_league_info(league_id)
    
    if not league_info:
        await query.edit_message_text("❌ League information not found")
        return
    
    league_id, name, country, logo_url, team_count, upcoming_matches = league_info
    
    text = (
        f"🏆 *{name}*\n\n"
        f"🌍 Country: {country}\n"
        f"👥 Teams: {team_count or 'N/A'}\n"
        f"📅 Upcoming Matches: {upcoming_matches or 0}\n"
        f"🏷️ League ID: {league_id}\n\n"
    )
    
    # Get popular teams in this league
    cursor.execute("""
        SELECT t.name, COUNT(f.fixture_id) as match_count
        FROM teams t
        JOIN fixtures f ON t.team_id IN (f.home_team_id, f.away_team_id)
        WHERE f.league_id = ? 
        AND f.status = 'NS'
        AND datetime(f.start_time) > datetime('now', '-? minutes')
        GROUP BY t.team_id
        ORDER BY match_count DESC
        LIMIT 5
    """, (league_id, MATCH_GRACE_PERIOD_MINUTES))
    
    popular_teams = cursor.fetchall()
    
    if popular_teams:
        text += "⚽ *Popular Teams:*\n"
        for team_name, match_count in popular_teams:
            text += f"• {team_name} ({match_count} upcoming)\n"
    
    keyboard = [
        [InlineKeyboardButton("📅 View Matches", callback_data=f"league_{league_id}_0_0")],
        [InlineKeyboardButton("🔙 Back to Leagues", callback_data="menu_leagues_today")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ======================
# MAIN
# ======================
def main():
    init_db()
    start_scheduler()
    
    # Create image directory
    ensure_image_directory()
    # Clear expired cache on startup
    cache.clear_expired()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("apistats", apistats_command))
    app.add_handler(CommandHandler("apistats", apistats_command))

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("leagues", leagues_command))  # Changed from matches
    app.add_handler(CommandHandler("betslip", betslip_command))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(CommandHandler("mybets", betslip_command))
    
    # Deposit/Withdraw commands
    app.add_handler(CommandHandler("deposit", deposit_command))
    app.add_handler(CommandHandler("withdraw", withdraw_command))
    
    # NEW: Results command
    app.add_handler(CommandHandler("results", results_command))
    
    # Admin commands
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("transactions", admin_transactions))
    app.add_handler(CommandHandler("users", admin_balance))
    app.add_handler(CommandHandler("stats", admin_stats_command))
    app.add_handler(CommandHandler("checkadmin", check_admin))
    app.add_handler(CommandHandler("cleanup", admin_cleanup))
    
    # Debug command for match times
    app.add_handler(CommandHandler("debugtime", debug_match_time))
    
    # NEW: Debug command for odds adjustment
    app.add_handler(CommandHandler("debugodds", debug_odds))
    
    # Transaction status command for users
    app.add_handler(CommandHandler("mytx", check_transaction_status))

    # Callback query handlers - UPDATED FOR LEAGUE-FIRST NAVIGATION
    app.add_handler(CallbackQueryHandler(main_menu_handler, pattern="^menu_"))
    app.add_handler(CallbackQueryHandler(match_callback, pattern="^match_"))
    app.add_handler(CallbackQueryHandler(bet_callback, pattern="^bet_"))
    app.add_handler(CallbackQueryHandler(betslip_actions, pattern="^(clear_betslip|enter_stake)$"))
    app.add_handler(CallbackQueryHandler(remove_selection_callback, pattern="^remove_"))
    app.add_handler(CallbackQueryHandler(main_menu_handler, pattern="^back_"))
    
    # League navigation handlers
    app.add_handler(CallbackQueryHandler(show_league_matches, pattern="^league_"))
    app.add_handler(CallbackQueryHandler(search_matches, pattern="^search_matches$"))
    app.add_handler(CallbackQueryHandler(handle_search_team, pattern="^search_team$"))
    app.add_handler(CallbackQueryHandler(refresh_odds_handler, pattern="^refresh_odds_"))
    app.add_handler(CallbackQueryHandler(league_info_handler, pattern="^league_info_"))
    
    # Deposit/Withdraw callback handlers
    app.add_handler(CallbackQueryHandler(handle_deposit_method, pattern="^deposit_"))
    app.add_handler(CallbackQueryHandler(handle_withdraw_method, pattern="^withdraw_"))
    app.add_handler(CallbackQueryHandler(handle_admin_approval, pattern="^(approve|reject)_"))
    
    # Admin callback handlers
    app.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^admin_"))
    
    # Bet history pagination handlers
    app.add_handler(CallbackQueryHandler(view_older_bets_handler, pattern="^view_older_bets$"))
    app.add_handler(CallbackQueryHandler(bet_page_handler, pattern="^bet_page_"))
    
    # Test button handler
    app.add_handler(CallbackQueryHandler(test_button_handler, pattern="^test_button$"))
    
    # Pagination handlers for leagues - MUST COME BEFORE main_menu_handler
    app.add_handler(CallbackQueryHandler(show_leagues_menu, pattern="^leagues_page_"))
    app.add_handler(CallbackQueryHandler(show_leagues_menu, pattern="^refresh_leagues_"))
	
    # League types handler
    app.add_handler(CallbackQueryHandler(main_menu_handler, pattern="^leagues_type_"))
    # Main menu handler - This should come AFTER specific handlers
    app.add_handler(CallbackQueryHandler(main_menu_handler, pattern="^menu_"))
        # Handle noop (non-clickable buttons)
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern="^noop$"))


    
	
	    
    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    # Photo handler for deposit screenshots
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))

    print("🤖 Bot running with league-first navigation...")
    print(f"📁 Image directory: {os.path.abspath('transaction_images')}")
    print(f"👑 Admin ID: {ADMIN_USER_ID}")
    print(f"💵 Minimum Deposit: {MIN_DEPOSIT}")
    print(f"💵 Minimum Withdrawal: {MIN_WITHDRAWAL}")
    print(f"⏰ Match Grace Period: {MATCH_GRACE_PERIOD_MINUTES} minutes")
    print(f"📊 Odds Adjustment: -{ODDS_ADJUSTMENT}")
    print("🏆 League-first navigation enabled!")
    print("🎯 Now supporting Over/Under 1.5, 2.5, 3.5 betting alongside 1X2!")
    print("📊 Enhanced bet history with detailed selections!")
    print("🔍 Added team search functionality!")
    print("📊 Match results feature added! Use /results or click 'Match Results' in main menu")
    print("📄 League pagination implemented!")
    print("🇺🇳 Country flag system enhanced!")
    print("🕒 Match time validation enabled!")
    print("📊 Odds adjustment system implemented!")
    app.run_polling()

if __name__ == "__main__":
    main()
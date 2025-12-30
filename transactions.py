# transactions.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from db import cursor, conn
from config import ADMIN_USER_ID, TELEBIRR_ACCOUNT, CBE_ACCOUNT
from datetime import datetime

# ======================
# DEPOSIT FUNCTIONS
# ======================
async def start_deposit(update, context):
    """Show deposit method options"""
    keyboard = [
        [
            InlineKeyboardButton("📱 Telebirr", callback_data="deposit_telebirr"),
            InlineKeyboardButton("🏦 CBE", callback_data="deposit_cbe")
        ],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_main")]
    ]
    
    await update.message.reply_text(
        "💰 *Choose Deposit Method:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_deposit_method(update, context):
    """Handle deposit method selection"""
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
        f"📱 *Account Number:* `{account}`\n\n"
        f"📝 *Instructions:*\n"
        f"1. Send money to the account above\n"
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

async def handle_deposit_screenshot(update, context):
    """Handle deposit screenshot from user"""
    if not context.user_data.get("awaiting_deposit_screenshot"):
        return
    
    user = update.effective_user
    method = context.user_data.get("deposit_method", "telebirr")
    
    # Get the photo file ID
    photo_file = update.message.photo[-1].file_id
    
    # Save transaction as pending
    cursor.execute("""
        INSERT INTO transactions 
        (user_id, username, type, method, status, screenshot_id)
        VALUES (?, ?, 'deposit', ?, 'pending', ?)
    """, (user.id, user.username, method, photo_file))
    conn.commit()
    
    # Get transaction ID
    transaction_id = cursor.lastrowid
    
    # Forward to admin
    admin_message = (
        f"📥 *NEW DEPOSIT REQUEST*\n\n"
        f"👤 User: @{user.username}\n"
        f"🆔 ID: `{user.id}`\n"
        f"💰 Method: {method.upper()}\n"
        f"📋 Transaction: #{transaction_id}\n\n"
        f"*Actions:*"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_deposit_{transaction_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_deposit_{transaction_id}")
        ]
    ]
    
    # Send photo and buttons to admin
    from bot import app  # We'll need to get the bot instance
    
    # We need to forward the photo first, then send the buttons
    # For simplicity, we'll just send the message
    # In production, you'd want to forward the actual photo
    
    # Clear the awaiting state
    context.user_data["awaiting_deposit_screenshot"] = False
    
    await update.message.reply_text(
        "✅ *Screenshot Received!*\n\n"
        "Your deposit request has been sent to admin for approval.\n"
        "You will be notified when it's processed.",
        parse_mode="Markdown"
    )
    
    # Send notification to admin (simplified - in real app, forward photo)
    await update.message.bot.send_message(
        chat_id=ADMIN_USER_ID,
        text=f"📸 New deposit screenshot from @{user.username}\n"
             f"Transaction ID: #{transaction_id}\n"
             f"Check database for screenshot ID: {photo_file}"
    )
    
    await update.message.bot.send_message(
        chat_id=ADMIN_USER_ID,
        text=admin_message,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ======================
# WITHDRAWAL FUNCTIONS
# ======================
async def start_withdraw(update, context):
    """Start withdrawal process"""
    # Check user balance first
    cursor.execute(
        "SELECT balance FROM users WHERE user_id=?",
        (update.effective_user.id,)
    )
    row = cursor.fetchone()
    
    if not row:
        await update.message.reply_text("❌ User not found")
        return
    
    balance = row[0]
    
    if balance <= 0:
        await update.message.reply_text("❌ Insufficient balance for withdrawal")
        return
    
    await update.message.reply_text(
        f"💵 *Withdrawal*\n\n"
        f"💰 Available Balance: `{balance}`\n\n"
        f"*Enter withdrawal amount:*",
        parse_mode="Markdown"
    )
    
    context.user_data["awaiting_withdraw_amount"] = True

async def handle_withdraw_amount(update, context):
    """Handle withdrawal amount input"""
    if not context.user_data.get("awaiting_withdraw_amount"):
        return
    
    try:
        amount = float(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number")
        return
    
    # Check balance
    cursor.execute(
        "SELECT balance FROM users WHERE user_id=?",
        (update.effective_user.id,)
    )
    row = cursor.fetchone()
    
    if not row:
        await update.message.reply_text("❌ User not found")
        context.user_data["awaiting_withdraw_amount"] = False
        return
    
    balance = row[0]
    
    if amount > balance:
        await update.message.reply_text(f"❌ Insufficient balance. Available: {balance}")
        return
    
    if amount < 10:  # Minimum withdrawal
        await update.message.reply_text("❌ Minimum withdrawal is 10")
        return
    
    # Store amount and show method selection
    context.user_data["withdraw_amount"] = amount
    context.user_data["awaiting_withdraw_amount"] = False
    
    keyboard = [
        [
            InlineKeyboardButton("📱 Telebirr", callback_data="withdraw_telebirr"),
            InlineKeyboardButton("🏦 CBE", callback_data="withdraw_cbe")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="back_main")]
    ]
    
    await update.message.reply_text(
        f"💵 *Withdrawal Amount:* `{amount}`\n\n"
        f"*Select withdrawal method:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_withdraw_method(update, context):
    """Handle withdrawal method selection"""
    query = update.callback_query
    await query.answer()
    
    method = query.data.replace("withdraw_", "")
    amount = context.user_data.get("withdraw_amount", 0)
    user = query.from_user
    
    if amount <= 0:
        await query.edit_message_text("❌ Invalid amount")
        return
    
    # Ask for account number
    context.user_data["withdraw_method"] = method
    context.user_data["awaiting_withdraw_account"] = True
    
    method_name = "Telebirr" if method == "telebirr" else "CBE"
    
    await query.edit_message_text(
        f"💵 *Withdrawal Details*\n\n"
        f"💰 Amount: `{amount}`\n"
        f"📱 Method: {method_name}\n\n"
        f"*Enter your {method_name} account number:*",
        parse_mode="Markdown"
    )

async def handle_withdraw_account(update, context):
    """Handle withdrawal account number"""
    if not context.user_data.get("awaiting_withdraw_account"):
        return
    
    account_number = update.message.text.strip()
    amount = context.user_data.get("withdraw_amount", 0)
    method = context.user_data.get("withdraw_method", "telebirr")
    user = update.effective_user
    
    if not account_number or len(account_number) < 5:
        await update.message.reply_text("❌ Please enter a valid account number")
        return
    
    # Check balance again
    cursor.execute(
        "SELECT balance FROM users WHERE user_id=?",
        (user.id,)
    )
    row = cursor.fetchone()
    
    if not row:
        await update.message.reply_text("❌ User not found")
        context.user_data["awaiting_withdraw_account"] = False
        return
    
    balance = row[0]
    
    if amount > balance:
        await update.message.reply_text(f"❌ Insufficient balance. Available: {balance}")
        context.user_data["awaiting_withdraw_account"] = False
        return
    
    # Save withdrawal request
    cursor.execute("""
        INSERT INTO transactions 
        (user_id, username, type, amount, method, status, account_number)
        VALUES (?, ?, 'withdraw', ?, ?, 'pending', ?)
    """, (user.id, user.username, amount, method, account_number))
    conn.commit()
    
    transaction_id = cursor.lastrowid
    
    # Notify admin
    method_name = "Telebirr" if method == "telebirr" else "CBE"
    
    admin_message = (
        f"📤 *NEW WITHDRAWAL REQUEST*\n\n"
        f"👤 User: @{user.username}\n"
        f"🆔 ID: `{user.id}`\n"
        f"💰 Amount: `{amount}`\n"
        f"📱 Method: {method_name}\n"
        f"📋 Account: `{account_number}`\n"
        f"📋 Transaction: #{transaction_id}\n\n"
        f"*Actions:*"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_withdraw_{transaction_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_withdraw_{transaction_id}")
        ]
    ]
    
    await update.message.bot.send_message(
        chat_id=ADMIN_USER_ID,
        text=admin_message,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Clear context
    context.user_data["awaiting_withdraw_account"] = False
    context.user_data["withdraw_amount"] = 0
    context.user_data["withdraw_method"] = None
    
    await update.message.reply_text(
        "✅ *Withdrawal Request Sent!*\n\n"
        "Your withdrawal request has been sent to admin for approval.\n"
        "You will be notified when it's processed.",
        parse_mode="Markdown"
    )

# ======================
# ADMIN FUNCTIONS
# ======================
async def handle_admin_approval(update, context):
    """Handle admin approval/rejection"""
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
        SELECT user_id, username, type, amount, method, account_number
        FROM transactions 
        WHERE transaction_id=? AND status='pending'
    """, (transaction_id,))
    
    transaction = cursor.fetchone()
    
    if not transaction:
        await query.edit_message_text("❌ Transaction not found or already processed")
        return
    
    user_id, username, trans_type, amount, method, account_number = transaction
    
    if action == "approve":
        if trans_type == "deposit":
            # Add balance to user
            cursor.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id=?",
                (amount if amount else 0, user_id)
            )
            status = "approved"
            user_message = f"✅ *Deposit Approved!*\n\n💰 {amount if amount else 'Amount'} has been added to your balance."
        
        elif trans_type == "withdraw":
            # Deduct balance from user
            cursor.execute(
                "UPDATE users SET balance = balance - ? WHERE user_id=?",
                (amount, user_id)
            )
            status = "approved"
            user_message = f"✅ *Withdrawal Approved!*\n\n💰 {amount} has been sent to your {method} account."
    
    else:  # reject
        status = "rejected"
        if trans_type == "deposit":
            user_message = f"❌ *Deposit Rejected*\n\nYour deposit request was rejected by admin."
        else:
            user_message = f"❌ *Withdrawal Rejected*\n\nYour withdrawal request was rejected by admin."
    
    # Update transaction status
    cursor.execute("""
        UPDATE transactions 
        SET status=?, processed_at=CURRENT_TIMESTAMP, processed_by=?
        WHERE transaction_id=?
    """, (status, update.effective_user.id, transaction_id))
    conn.commit()
    
    # Notify user
    try:
        await query.bot.send_message(
            chat_id=user_id,
            text=user_message,
            parse_mode="Markdown"
        )
    except:
        pass  # User might have blocked the bot
    
    # Update admin message
    await query.edit_message_text(
        f"✅ *Transaction Processed*\n\n"
        f"Transaction #{transaction_id} has been {status}.\n"
        f"User @{username} has been notified.",
        parse_mode="Markdown"
    )

# ======================
# ADMIN COMMANDS
# ======================
async def admin_panel(update, context):
    """Admin panel for managing transactions"""
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Access denied")
        return
    
    # Get pending transactions
    cursor.execute("""
        SELECT transaction_id, type, user_id, username, amount, method, created_at
        FROM transactions 
        WHERE status='pending'
        ORDER BY created_at DESC
    """)
    
    pending = cursor.fetchall()
    
    text = "🛠 *ADMIN PANEL*\n\n"
    
    if pending:
        text += f"📋 *Pending Transactions:* {len(pending)}\n\n"
        for trans in pending[:10]:  # Show last 10
            trans_id, trans_type, user_id, username, amount, method, created_at = trans
            text += f"#{trans_id} - {trans_type.upper()} - @{username}\n"
            text += f"   Amount: {amount if amount else 'Not specified'}\n"
            text += f"   Method: {method}\n"
            text += f"   Time: {created_at}\n\n"
    else:
        text += "✅ No pending transactions\n\n"
    
    # Get stats
    cursor.execute("""
        SELECT 
            COUNT(*) as total_transactions,
            SUM(CASE WHEN status='approved' AND type='deposit' THEN amount ELSE 0 END) as total_deposits,
            SUM(CASE WHEN status='approved' AND type='withdraw' THEN amount ELSE 0 END) as total_withdrawals
        FROM transactions
    """)
    
    stats = cursor.fetchone()
    
    if stats:
        total_trans, total_deposits, total_withdrawals = stats
        text += f"📊 *Statistics*\n"
        text += f"Total Transactions: {total_trans}\n"
        text += f"Total Deposits: {total_deposits or 0}\n"
        text += f"Total Withdrawals: {total_withdrawals or 0}\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def admin_balance(update, context):
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
    
    await update.message.reply_text(text, parse_mode="Markdown")
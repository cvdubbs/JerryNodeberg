import discord
import re
import aiohttp
import asyncio
import os
import datetime
from datetime import timedelta
from dotenv import load_dotenv
load_dotenv()

discord_bot_token = os.getenv("discord_bot_token")

intents = discord.Intents.default()
intents.message_content = True  # Needed to read messages

bot = discord.Client(intents=intents)

DEXSCREENER_API = "https://api.dexscreener.com/token-pairs/v1/Solana/"
DEX_ORDERS_API = "https://api.dexscreener.com/orders/v1/solana/"

# Dictionary to track monitoring tasks for each token
monitoring_tasks = {}


def shorten_address(addr):
    return f"{addr[:4]}...{addr[-4:]}"


def get_age_string(timestamp_ms):
    created = datetime.datetime.utcfromtimestamp(timestamp_ms / 1000)
    now = datetime.datetime.utcnow()
    delta = now - created
    hours = delta.total_seconds() // 3600
    minutes = (delta.total_seconds() % 3600) // 60
    return f"{int(hours)}h {int(minutes)}m old"


def build_jerry_embed(pair):
    base = pair["baseToken"]
    quote = pair["quoteToken"]
    info = pair.get("info", {})
    price = float(pair.get("priceUsd", 0))
    price_change_1h = pair.get("priceChange", {}).get("h1", 0)
    price_change_24h = pair.get("priceChange", {}).get("h24", 0)
    txns = pair.get("txns", {}).get("h1", {})
    volume = pair.get("volume", {}).get("h1", 0)
    liquidity = pair.get("liquidity", {}).get("usd", 0)
    fdv = pair.get("fdv", 0)
    url = pair.get("url")
    dex = pair.get("dexId", "N/A").capitalize()
    chain = pair.get("chainId", "N/A").capitalize()
    created_at = get_age_string(pair.get("pairCreatedAt", 0))

    embed = discord.Embed(
        title=f"{base['name']} [${(fdv/1000):,.0f}k/{price_change_1h:.2f}%] - {base['symbol']}/{quote['symbol']}",
        url=url,
        color=discord.Color.orange()
    )

    embed.set_author(name="🔍 Jerry - 🧾 Contact Address Information")
    embed.set_thumbnail(url=info.get("imageUrl"))

    embed.add_field(
        name="🌐 Chain / DEX",
        value=f"{chain} · {dex}",
        inline=True
    )
    embed.add_field(
        name="💲USD",
        value=f"${price:,.8f}",
        inline=True
    )
    embed.add_field(
        name="💧 Liq.",
        value=f"${(liquidity/1000):,.0f}k",
        inline=True
    )

    embed.add_field(
        name="🏷️ MC",
        value=f"${(fdv/1000):,.0f}k",
        inline=True
    )
    embed.add_field(
        name="🕐 Age",
        value=created_at,
        inline=True
    )

    embed.add_field(
        name="🔄 1H / 24H",
        value=f"**{price_change_1h:+.2f}% / {price_change_24h:+.2f}%**",
        inline=True
    )
    embed.add_field(
        name="💵 Volume 1h",
        value=f"${(volume/1000):,.2f}k",
        inline=True
    )
    embed.add_field(
        name="📊 1H Txns",
        value=f"🟢 {txns.get('buys', 0)} | 🔴 {txns.get('sells', 0)}",
        inline=True
    )

    embed.add_field(
        name="📄 Contract",
        value=f"```{base['address']}```",
        inline=False
    )

    embed.add_field(
        name="📱 Trade",
        value=(
            f"[B🐂](https://bullx.io/terminal?chainId=1399811149&address={base['address']}) "
            f"[P⚡](https://photon-sol.tinyastro.io/en/lp/{base['address']}) "
            f"[G🦎](https://gmgn.ai/sol/token/{base['address']}) "
            f"[A⚛️](https://axiom.trade/t/{base['address']}) "
            f"[B🌸](https://t.me/BloomSolanaEU2_bot?start=ref_RickBot_ca_{base['address']})"
        ),
        inline=True
    )

    embed.set_footer(text="📝 NOTE: Jerry is in alpha testing and an idiot. I know I am")

    return embed


# Detect contract addresses (basic check)
def extract_contract(message):
    patterns = [
        r"\b0x[a-fA-F0-9]{40}\b",                      # ETH/BSC
        r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b"             # Solana base58
    ]
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return match.group()
    return None


async def fetch_token_data(contract):
    async with aiohttp.ClientSession() as session:
        async with session.get(DEXSCREENER_API + contract) as response:
            if response.status == 200:
                return await response.json()
            return None


# DEX Payment Monitoring Functions
async def check_dex_status(token_address):
    """Check DEX screener payment status for a token"""
    url = f"{DEX_ORDERS_API}{token_address}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"DEX API Response for {token_address}: {data}")  # Debug logging
                    
                    if isinstance(data, list) and len(data) > 0:
                        entry = data[0]
                        status = entry.get('status', 'unknown')
                        entry_type = entry.get('type', 'unknown')
                        
                        # Map different statuses to our expected format
                        if status == 'approved' and entry_type == 'tokenProfile':
                            return 'paid'
                        elif status == 'pending':
                            return 'processing'
                        elif status == 'rejected':
                            return 'not_paid'
                        else:
                            return status  # Return original status if not mapped
                            
                    elif isinstance(data, dict):
                        status = data.get('status', 'unknown')
                        # Handle single object response
                        if status == 'approved':
                            return 'paid'
                        elif status == 'pending':
                            return 'processing'
                        elif status == 'rejected':
                            return 'not_paid'
                        else:
                            return status
                    else:
                        return 'not_found'
                elif response.status == 404:
                    return 'not_found'
                else:
                    return 'api_error'
    except Exception as e:
        print(f"Error checking DEX status: {e}")
        return 'error'


async def monitor_dex_payment(channel, token_address, start_time, author):
    """Monitor DEX payment status with periodic checks"""
    
    # Initial status check
    initial_status = await check_dex_status(token_address)
    
    # Send initial status message
    embed = discord.Embed(
        title="🔍 DEX Screener Status Check",
        color=0xFFD700,
        timestamp=datetime.datetime.utcnow()
    )
    
    status_emoji = {
        'paid': '✅',
        'processing': '🔄',
        'pending': '⏳',
        'not_paid': '❌',
        'not_found': '🚫',
        'error': '⚠️',
        'api_error': '⚠️',
        'unknown': '❓'
    }
    
    status_text = {
        'paid': 'Paid ✅',
        'processing': 'Processing 🔄',
        'pending': 'Pending ⏳',
        'not_paid': 'Not Paid ❌',
        'not_found': 'Not Found 🚫',
        'error': 'API Error ⚠️',
        'api_error': 'API Error ⚠️',
        'unknown': 'Unknown Status ❓'
    }
    
    embed.add_field(
        name="Current Status",
        value=f"{status_emoji.get(initial_status, '❓')} {status_text.get(initial_status, 'Unknown')}",
        inline=False
    )
    
    embed.add_field(
        name="Token Address",
        value=f"`{token_address}`",
        inline=False
    )
    
    # If already paid, no need to monitor
    if initial_status == 'paid':
        embed.color = 0x00FF00  # Green
        embed.add_field(name="✅ Complete", value="DEX listing is already paid!", inline=False)
        await channel.send(f"{author.mention} ", embed=embed)
        return
    
    # Send initial status
    status_message = await channel.send(f"{author.mention} ", embed=embed)
    
    # If status is not worth monitoring, stop here
    if initial_status in ['error', 'api_error']:
        return
    
    # Start monitoring loop
    last_status = initial_status
    end_time = start_time + timedelta(hours=1)  # 1 hour from when contract was posted
    
    while datetime.datetime.utcnow() < end_time:
        await asyncio.sleep(5)  # Wait 5 seconds
        
        current_status = await check_dex_status(token_address)
        
        # Check if status changed
        if current_status != last_status and current_status in ['processing', 'paid']:
            
            # Create update embed
            update_embed = discord.Embed(
                title="🔄 DEX Status Update",
                color=0x00FF00 if current_status == 'paid' else 0xFFA500,
                timestamp=datetime.datetime.utcnow()
            )
            
            update_embed.add_field(
                name="Status Changed!",
                value=f"{status_emoji.get(last_status, '❓')} {status_text.get(last_status, 'Unknown')} → {status_emoji.get(current_status, '❓')} {status_text.get(current_status, 'Unknown')}",
                inline=False
            )
            
            update_embed.add_field(
                name="Token Address",
                value=f"`{token_address}`",
                inline=False
            )
            
            if current_status == 'paid':
                update_embed.add_field(
                    name="🎉 Success!",
                    value="DEX screener listing is now paid and should be live!",
                    inline=False
                )
                
                # Add DEX screener link
                update_embed.add_field(
                    name="📊 View on DEX Screener",
                    value=f"[Click Here](https://dexscreener.com/solana/{token_address})",
                    inline=False
                )
            
            elif current_status == 'processing':
                update_embed.add_field(
                    name="⏳ Processing",
                    value="Payment is being processed. Should be live soon!",
                    inline=False
                )
            
            await channel.send(f"{author.mention} 🚨 Token payment status updated!", embed=update_embed)
            
            # If paid, stop monitoring
            if current_status == 'paid':
                break
                
            last_status = current_status
    
    # Clean up the monitoring task
    if token_address in monitoring_tasks:
        del monitoring_tasks[token_address]


async def start_dex_monitoring(channel, token_address, author):
    # Cancel existing monitoring for this token if it exists
    if token_address in monitoring_tasks:
        monitoring_tasks[token_address].cancel()
    
    # Record the start time
    start_time = datetime.datetime.utcnow()
    
    # Create and start the monitoring task
    task = asyncio.create_task(monitor_dex_payment(channel, token_address, start_time, author))
    monitoring_tasks[token_address] = task
    
    try:
        await task
    except asyncio.CancelledError:
        pass


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    if message.author.name == "Rick":  # or use .id == RICK_ID
        return
    
    if message.author.name == "Solami Scanner":  # or use .id == RICK_ID
        return

    contract = extract_contract(message.content)
    if not contract:
        return

    await message.channel.send(f"🔍 Looking up `{contract}` on Dexscreener...")

    data = await fetch_token_data(contract)

    if not data or not isinstance(data, list):
        await message.channel.send("❌ Unexpected API response format.")
        return

    if len(data) == 0:
        await message.channel.send("❌ No trading pairs found.")
        return

    # Pick the best pair based on volume
    best_pair = max(data, key=lambda p: p.get("volume", {}).get("h24", 0))
    embed = build_jerry_embed(best_pair)

    # Send the main token information embed
    await message.channel.send(embed=embed)
    
    # Start DEX payment monitoring as a separate message
    await start_dex_monitoring(message.channel, contract, message.author)


bot.run(discord_bot_token)
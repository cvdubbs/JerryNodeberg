import discord
import re
import aiohttp
import asyncio
import os
import datetime
from dotenv import load_dotenv
load_dotenv()

discord_bot_token = os.getenv("discord_bot_token")

intents = discord.Intents.default()
intents.message_content = True  # Needed to read messages

bot = discord.Client(intents=intents)

DEXSCREENER_API = "https://api.dexscreener.com/token-pairs/v1/Solana/"


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
    # embed.add_field(
    #     name="📈 ATH",
    #     value=f"${'?.??'} (not provided)",
    #     inline=True
    # )
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


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.event
async def on_message(message):
    if message.author == bot.user:
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

    # base = best_pair["baseToken"]
    # quote = best_pair["quoteToken"]
    # price = best_pair.get("priceUsd", "N/A")
    # vol = best_pair.get("volume", {}).get("h24", 0)
    # fdv = best_pair.get("fdv", "N/A")
    # liq = best_pair.get("liquidity", {}).get("usd", "N/A")
    # dex = best_pair.get("dexId", "N/A")
    # chain = best_pair.get("chainId", "N/A")
    # url = best_pair.get("url", "#")
    # img = best_pair.get("info", {}).get("imageUrl")

    # embed = discord.Embed(
    #     title=f"{base.get('name')} ({base.get('symbol')})",
    #     description=f"[View on Dexscreener]({url})",
    #     color=discord.Color.blue()
    # )
    # embed.set_thumbnail(url=img)
    # embed.add_field(name="💲 Price", value=f"${float(price):,.8f}", inline=True)
    # embed.add_field(name="📈 Volume (24h)", value=f"${vol:,.2f}", inline=True)
    # embed.add_field(name="💧 Liquidity", value=f"${liq:,.2f}", inline=True)
    # embed.add_field(name="🔗 DEX", value=dex, inline=True)
    # embed.add_field(name="🌐 Chain", value=chain.capitalize(), inline=True)
    # embed.add_field(name="🏷️ FDV", value=f"${int(fdv):,}" if isinstance(fdv, (int, float)) else "N/A", inline=True)

    await message.channel.send(embed=embed)

bot.run(discord_bot_token)
 
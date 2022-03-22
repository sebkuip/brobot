import discord
from discord import app_commands
import asyncpg
from dotenv import load_dotenv
from os import getenv
import re
import asyncio

load_dotenv(".env")

token = getenv("TOKEN")

client = discord.Client(intents=discord.Intents.all())
tree: app_commands.CommandTree = app_commands.CommandTree(client)

#database
HOST = getenv("HOST")
PORT = getenv("PORT")
DATABASE = getenv("DATABASE")
USER = getenv("USER")
PASSWORD = getenv("PASSWORD")

@client.event
async def on_ready():
    print(f'{client.user} has connected to Discord!')
    print(f'Username is {client.user.name}')
    print(f'ID is {client.user.id}')
    print(f'Keep this window open to keep the client running.')

    #database
    print('Connecting to database')
    await get_db()

async def get_db():
    client.pool = await asyncpg.create_pool(host=HOST, port=PORT, database=DATABASE, user=USER, password=PASSWORD)

    async with client.pool.acquire() as con:
        result = await con.fetchrow('SELECT version()')
        db_version = result[0]
        print(f'Database version: {db_version}')

@client.event
async def on_message(m: discord.Message):
    if m.author.bot:
        return

    if re.search(r"((\W)|(^))bro((\W)|($))", m.content.lower()) is not None:
        async with client.pool.acquire() as con:
            await con.execute("INSERT INTO stats(uid, count) VALUES($1, 1) ON CONFLICT (uid) DO UPDATE SET count = stats.count + 1 WHERE stats.uid = $1", m.author.id)


@tree.command(guild=discord.Object(id=955325522915758100), description="This is a test command")
async def test(interaction: discord.Interaction):
    await interaction.response.send_message("Thanks for testing")

@tree.command(guild=discord.Object(id=955325522915758100), description="Get bro count from user")
async def brocount(interaction: discord.Interaction, user: discord.User):
    async with client.pool.acquire() as con:
        result = await con.fetchrow("SELECT count FROM stats WHERE uid = $1", user.id)
        if result is None:
            await interaction.response.send_message(f"{user.name} has not said bro yet")
        else:
            await interaction.response.send_message(f"{user.name} has {result[0]} bros")

class LeaderBoard(discord.ui.View):
    def __init__(self, client, interaction, page, data, embed):
        super().__init__()
        self.client = client
        self.interaction = interaction
        self.page = page
        self.curr_embed = embed

        self.timeout = 20
        self.message = None

        if page == 1:
            button = discord.utils.get(self.children, custom_id="pg_bck")
            button.disabled = True

        if len(data) < 10:
            button = discord.utils.get(self.children, custom_id="pg_fwd")
            button.disabled = True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            await self.interaction.edit_original_message(
                content="timed out", embed=self.curr_embed, view=self
            )
        except discord.NotFound:
            pass

    @discord.ui.button(
        label="<<", style=discord.ButtonStyle.blurple, custom_id="pg_bck"
    )
    async def page_back(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        if not self.interaction.user == interaction.user:
            await interaction.response.send_message(
                "You cannot respond to this", ephemeral=True
            )
            return

        if self.page == 2:
            button.disabled = True

        self.page -= 1

        offset = (self.page - 1) * 10

        async with self.client.pool.acquire() as con:
            data = await con.fetch(
                "SELECT * FROM stats ORDER BY count DESC LIMIT 10 OFFSET $1", offset
            )

        embed = discord.Embed(
            title="Leaderboard",
            description=f"page {self.page}",
            color=discord.Color.blurple(),
        )
        for i, entry in enumerate(data):
            user = self.client.get_user(entry["uid"]) or await self.client.fetch_user(
                entry["uid"]
            )
            embed.add_field(
                name=str(user),
                value=f"Rank: {i+1+(self.page-1)*10}\nTotal bros: {entry['count']}",
                inline=False,
            )
        if len(data) == 10:
            forward = discord.utils.get(self.children, custom_id="pg_fwd")
            forward.disabled = False
        await self.interaction.edit_original_message(embed=embed, view=self)
        self.curr_embed = embed
        await interaction.response.defer()

    @discord.ui.button(
        label=">>", style=discord.ButtonStyle.blurple, custom_id="pg_fwd"
    )
    async def page_forward(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        if not self.interaction.user == interaction.user:
            msg = await self.interaction.original_message()
            await msg.send_message(
                "You cannot respond to this", ephemeral=True
            )
            return

        if self.page == 1:
            back = discord.utils.get(self.children, custom_id="pg_bck")
            back.disabled = False

        self.page += 1

        offset = (self.page - 1) * 10

        async with self.client.pool.acquire() as con:
            data = await con.fetch(
                "SELECT * FROM stats ORDER BY count DESC LIMIT 10 OFFSET $1", offset
            )

        embed = discord.Embed(
            title="Leaderboard",
            description=f"page {self.page}",
            color=discord.Color.blurple(),
        )
        for i, entry in enumerate(data):
            user = self.client.get_user(entry["uid"]) or await self.client.fetch_user(
                entry["uid"]
            )
            embed.add_field(
                name=str(user),
                value=f"Rank: {i+1+(self.page-1)*10}\nTotal bros: {entry['count']}",
                inline=False,
            )
        if len(data) < 10:
            button.disabled = True
        await self.interaction.edit_original_message(embed=embed, view=self)
        self.curr_embed = embed
        await interaction.reponse.defer()

    @discord.ui.button(emoji="🗑️", style=discord.ButtonStyle.danger)
    async def cancel(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        if not self.interaction.user == interaction.user:
            await interaction.send_message(
                "You cannot respond to this", ephemeral=True
            )
            return

        await self.interaction.delete_original_message()
        await interaction.response.defer()

@tree.command(guild=discord.Object(id=955325522915758100), description="Show the brocount leaderboard")
async def leaderboard(interaction: discord.Interaction, page: int = 1):
    page = 1 if page < 1 else page
    offset = (page - 1) * 10

    async with client.pool.acquire() as con:
        data = await con.fetch(
            "SELECT * FROM stats ORDER BY count DESC LIMIT 10 OFFSET $1", offset
        )

    embed = discord.Embed(
        title="Leaderboard",
        description=f"page {page}",
        color=discord.Color.blurple(),
    )
    for i, entry in enumerate(data):
        user = client.get_user(entry["uid"]) or await client.fetch_user(
            entry["uid"]
        )
        embed.add_field(
            name=str(user),
            value=f"Rank: {i+1+(page-1)*10}\nTotal bros: {entry['count']}",
            inline=False,
        )

    lbview = LeaderBoard(client, interaction, page, data, embed)
    await interaction.response.send_message(embed=embed, view=lbview)

def check_owner():
    def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.id == 234649992357347328
    return app_commands.check(predicate)

@tree.command(guild=discord.Object(id=955325522915758100), description="Sync the slash commands. Owner only.")
@check_owner()
async def sync(interaction: discord.Interaction):
    await tree.sync(guild=discord.Object(id=955325522915758100))
    await interaction.response.send_message("Synced", ephemeral=True)

@sync.error
async def on_error(interaction: discord.Interaction, error: Exception):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(f'You are not the owner of this bot.', ephemeral=True)
        return

client.run(token)

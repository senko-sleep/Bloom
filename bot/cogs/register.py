import asyncio
import csv
import difflib
import json
import os
import re
import multiprocessing as mp
from functools import partial


from fuzzywuzzy import fuzz
from tqdm import tqdm, asyncio as async_tqdm
from motor.motor_asyncio import AsyncIOMotorClient
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor



from lib.imports.discord import *
from lib.imports.logger import *
from lib.utils.cogs.register import * 
from lib.config.const import primary_color
from bot.token import use_test_bot as ut 




class Ping_Pokemon(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.shiny_collection = "shiny_hunt"
        self.collection_collection = "collection"
        self.type_collection = "type_ping"
        self.quest_collection = "quest_ping"

        self.pokemon_names_file = r"data\bot\cogs\register\pokemon_names.csv"
        self.pokemon_types_file = r"data\bot\cogs\register\pokemon_types.csv"
        self.pokemon_rarity_file = r"bot\cogs\register\rarity.csv"
        self.pokemon_description_file = None
        self.embed_default_color = primary_color()
        self.RESULTS_PER_PAGE = 10
        self.MAX_POKEMON = 50

        self.success_emoji = "<:green:1261639410181476443>"
        self.error_emoji = "<:red:1261639413943762944>"
        self.check_emoji = "✅"
        self.cross_emoji = "❌"
        self.star_emoji = "⭐"
        self.globe_emoji = "🌍"
        self.trash_emoji = "🗑️"

        try:
            self.mongo = MongoHelper(AsyncIOMotorClient(os.getenv("MONGO_URI"))["Commands"]["pokemon"])
        except:
            print("⚠️ MongoDB connection failed.")
            self.mongo = None

        try:
            self.pe = Pokemon_Emojis(bot)
            self.ph = PokemonNameHelper()
        except:
            print("⚠️ Pokemon helper classes not loaded.")
            self.pe = None
            self.ph = None

        self.data_manager = PokemonDataManager(
            mongo_client=self.mongo,
            pokemon_names_csv=self.pokemon_names_file,
            pokemon_types_csv=self.pokemon_types_file,
            pokemon_rarity_csv=self.pokemon_rarity_file
        )

        self.embed_manager = PokemonEmbedManager(
            embed_default_color=self.embed_default_color,
            icons={
                "success": self.check_emoji,
                "error": self.cross_emoji,
                "exists": "⍻",
                "removed": "−",
                "not_found": "?"
            },
            results_per_page=self.RESULTS_PER_PAGE,
            chunk_size=15
        )

        self.collection_handler = PokemonCollectionHandler(
            data_manager=self.data_manager,
            embed_manager=self.embed_manager,
            pokemon_emojis=self.pe,
            pokemon_subcogs=self.ph,
            max_pokemon=self.MAX_POKEMON
        )

        self.flag_parser = AdvancedStringFlagParser()
        self.pokemon_types = self.load_pokemon_types()

    def load_pokemon_types(self):
        types = set()
        try:
            with open(self.pokemon_types_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if 'types' in row and row['types']:
                        pokemon_types = row['types'].strip('"').split(',')
                        for ptype in pokemon_types:
                            types.add(ptype.strip().lower())
        except FileNotFoundError:
            print(f"⚠️ Pokemon types file not found: {self.pokemon_types_file}")
            types = {
                "normal", "fire", "water", "electric", "grass", "ice",
                "fighting", "poison", "ground", "flying", "psychic", "bug",
                "rock", "ghost", "dragon", "dark", "steel", "fairy"
            }
        return sorted(list(types))

    def load_quest_regions(self):
        return {
            "kanto", "johto", "hoenn", "sinnoh", "unova", "kalos",
            "alola", "galar", "hisui", "paldea"
        }

    async def get_server_config(self, guild_id: int) -> dict:
        if not self.mongo:
            return {}
        config = await self.mongo.db["server_config"].find_one({"guild_id": guild_id}) or {}
        return config

    @commands.command(name="type_ping", aliases=["tp"])
    async def type_ping(self, ctx):
        user_id = ctx.author.id
        try:
            current_types_data = await self.mongo.db["type_ping_types"].find({"user_id": user_id}).to_list(None)
            current_types = [entry["type"] for entry in current_types_data]
        except Exception:
            current_types = []

        view = PokemonTypeButtons(user_id, "type_ping", self.mongo, self.pokemon_types, current_types)
        embed = view._create_embed(ctx=ctx)
        await ctx.reply(embed=embed, view=view, mention_author=False)

    @commands.hybrid_command(name="quest_ping", aliases=["qp"])
    async def quest_ping(self, ctx):
        user_id = ctx.author.id
        try:
            current_regions_data = await self.mongo.db[self.quest_collection].find_one({"user_id": user_id})
            current_regions = current_regions_data.get("regions", []) if current_regions_data else []
        except Exception:
            current_regions = []

        available_regions = sorted(list(self.load_quest_regions()))
        view = PokemonRegionButtons(user_id, self.quest_collection, self.mongo, available_regions, current_regions)
        embed = view._create_embed(ctx=ctx)
        await ctx.reply(embed=embed, view=view, mention_author=False)

    @app_commands.command(
        name="specialping",
        description="Set or remove role pings for rare or regional Pokémon spawns."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        ping_type="Select the ping category: rare or regional Pokémon.",
        role="Role to mention for the selected ping type (leave empty to remove)."
    )
    @app_commands.choices(ping_type=[
        app_commands.Choice(name="Rare Pokémon", value="rare"),
        app_commands.Choice(name="Regional Pokémon", value="regional"),
    ])
    async def special_ping(
        self,
        interaction: discord.Interaction,
        ping_type: app_commands.Choice[str],
        role: discord.Role | None = None
    ):
        guild_id = interaction.guild.id
        key = f"{ping_type.value}_role"

        try:
            config = await self.get_server_config(guild_id)

            if role:
                config[key] = role.id
                message = f"{ping_type.name} ping role set to {role.mention}."
            else:
                config.pop(key, None)
                message = f"{ping_type.name} ping role has been removed."

            await self.mongo.db["server_config"].update_one(
                {"guild_id": guild_id},
                {"$set": config},
                upsert=True
            )

            rare_role = interaction.guild.get_role(config.get("rare_role"))
            regional_role = interaction.guild.get_role(config.get("regional_role"))

            embed = discord.Embed(
                title="Special Ping Configuration Updated",
                description=message,
                color=discord.Color.default()
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.add_field(
                name="Current Ping Roles",
                value=(
                    f"**Rare Pokémon:** {rare_role.mention if rare_role else 'Not set'}\n"
                    f"**Regional Pokémon:** {regional_role.mention if regional_role else 'Not set'}"
                ),
                inline=False
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            error_embed = discord.Embed(
                title="Error",
                description=f"Failed to update ping roles: `{e}`",
                color=discord.Color.red()
            )
            error_embed.set_thumbnail(url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=error_embed, ephemeral=True)

    @special_ping.error
    async def special_ping_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        embed = discord.Embed(
            title="Error in specialping command",
            description=f"```py\n{error}```",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.command(name="shiny_hunt", aliases=["sh"])
    async def shiny_hunt(self, ctx, action: str = None, *, pokemon: str = None):
        prefix = ctx.prefix

        if action == "help":
            desc = (
                f"**Usage:**\n"
                f"`{prefix}sh` — View your current shiny hunt\n"
                f"`{prefix}sh <pokemon>` — Set shiny target\n"
                f"`{prefix}sh add <pokemon>` — Add to shiny hunt\n"
                f"`{prefix}sh remove` — Remove shiny hunt\n"
                f"`{prefix}sh remove <pokemon>` — Remove specific target\n"
                f"`{prefix}sh list` — List shiny hunt targets\n"
                f"`{prefix}sh clear` — Clear all shiny targets\n\n"
            )
            return await ctx.reply(embed=discord.Embed(title="Shiny Hunt Help", description=desc, color=self.embed_default_color), mention_author=False)

        if not action and not pokemon:
            if not self.mongo:
                return await ctx.reply("❌ Database connection not available.", mention_author=False)
            cur = await self.mongo.list(self.shiny_collection, ctx.author.id)
            if not cur:
                return await ctx.reply(embed=discord.Embed(description="You don't have a shiny hunt set.", color=self.embed_default_color), mention_author=False)
            name = cur[0]
            pid = Pokemon_Subcogs.pokemon_name_to_id(name) if 'Pokemon_Subcogs' in globals() else None
            emoji = self.pe.get_emoji_for_pokemon(pid) if self.pe and pid else ""
            disp = self.data_manager.display_name_with_region(name)
            return await ctx.reply(embed=discord.Embed(description=f"You are currently shiny hunting: **{emoji} {disp}**", color=self.embed_default_color), mention_author=False)

        if action == "remove" and not pokemon:
            if not self.mongo:
                return await ctx.reply("❌ Database connection not available.", mention_author=False)
            await self.mongo.clear(self.shiny_collection, ctx.author.id)
            return await ctx.reply(embed=discord.Embed(description="🗑️ Your shiny hunt has been removed.", color=self.embed_default_color), mention_author=False)

        if action not in {"add", "remove", "list", "clear"}:
            full = f"{action} {pokemon}".strip() if pokemon else action
            if self.ph:
                full, _ = self.ph.transform_name(full)
            action, pokemon = "add", full

        flags = self.flag_parser.parse_flags_from_string(pokemon or "")
        await self.collection_handler.handle_collection(ctx, self.shiny_collection, action, pokemon=pokemon, flags_obj=flags, max_one=True)

    @commands.command(name="collection", aliases=["cl"])
    async def collection_string(self, ctx, *, args: str = "list"):
        try:
            action = "list"
            pokemon_names = ""
            args_lower = args.lower().strip()

            if args_lower.startswith(('add ', 'remove ', 'delete ', 'clear', 'help')):
                parts = args.split(' ', 1)
                action = parts[0].lower()
                if action == "delete":
                    action = "remove"
                remaining = parts[1] if len(parts) > 1 else ""
            else:
                remaining = args

            if action == "help":
                embed = PokemonHelpEmbed.generate_collection_help_embed(self, ctx)
                return await ctx.reply(embed=embed, mention_author=False)

            flags_dict = self.flag_parser.parse_flags_from_string(remaining)
            pokemon_names, _ = self.flag_parser.extract_pokemon_names_from_string(remaining, action)

            await self.collection_handler.handle_collection(
                ctx,
                self.collection_collection,
                action,
                pokemon=pokemon_names or None,
                flags_obj=flags_dict
            )

        except Exception as e:
            await ctx.reply(f"An error occurred while processing your command:\n`{type(e).__name__}: {e}`", mention_author=False)

    @commands.command(name="server_config", aliases=["sc"])
    @commands.has_permissions(manage_guild=True)
    async def server_config(self, ctx):
        embed = discord.Embed(
            title="Server Configuration",
            description="Configure server-wide Pokemon ping settings",
            color=self.embed_default_color
        )

        config = await self.get_server_config(ctx.guild.id)
        rare_role = ctx.guild.get_role(config.get("rare_role")) if config.get("rare_role") else None
        regional_role = ctx.guild.get_role(config.get("regional_role")) if config.get("regional_role") else None

        embed.add_field(
            name="Current Settings",
            value=f"**Rare Pokemon Role:** {rare_role.mention if rare_role else 'Not set'}\n"
                  f"**Regional Pokemon Role:** {regional_role.mention if regional_role else 'Not set'}",
            inline=False
        )

        view = ServerConfigView(ctx.guild.id, self.mongo)
        await ctx.reply(embed=embed, view=view, mention_author=False)



async def setup(bot):
    await bot.add_cog(Ping_Pokemon(bot))





import disnake
from disnake.ext import commands
import yt_dlp as youtube_dl
import asyncio
import requests

# Установите ваш токен и API ключ
TOKEN = ''
YOUTUBE_API_KEY = ''

# Настройка бота с необходимыми правами
intents = disnake.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# Опции для yt-dlp
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(disnake.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(disnake.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

class MusicQueue:
    def __init__(self):
        self.queue = []

    def add(self, source):
        self.queue.append(source)

    def pop(self):
        return self.queue.pop(0) if self.queue else None

    def peek(self):
        return self.queue[0] if self.queue else None

    def clear(self):
        self.queue.clear()

    def __len__(self):
        return len(self.queue)

music_queue = MusicQueue()

async def search_youtube(query):
    """Поиск видео на YouTube по запросу и возврат URL."""
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={query}&key={YOUTUBE_API_KEY}&type=video"
    response = requests.get(url).json()
    
    if 'items' in response and len(response['items']) > 0:
        video_id = response['items'][0]['id']['videoId']
        return f"https://www.youtube.com/watch?v={video_id}"
    return None

@bot.slash_command()
async def join(ctx: disnake.ApplicationCommandInteraction):
    """Присоединиться к голосовому каналу"""
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f"Присоединился к {channel}!")
    else:
        await ctx.send("Вы должны быть в голосовом канале для использования этой команды.")

@bot.slash_command()
async def leave(ctx: disnake.ApplicationCommandInteraction):
    """Покинуть голосовой канал"""
    if ctx.guild.voice_client:
        await ctx.guild.voice_client.disconnect()
        await ctx.send("Покинул голосовой канал.")
    else:
        await ctx.send("Бот не подключен к голосовому каналу.")

@bot.slash_command()
async def play(ctx: disnake.ApplicationCommandInteraction, query: str):
    """Воспроизвести песню по названию"""
    await ctx.send("Обрабатываю ваш запрос...")  # Уведомление о начале обработки
    try:
        youtube_url = await search_youtube(query)
        if youtube_url is None:
            await ctx.send("Не удалось найти видео на YouTube.")
            return

        player = await YTDLSource.from_url(youtube_url, loop=bot.loop, stream=True)
        music_queue.add(player)

        if not ctx.guild.voice_client.is_playing():
            await play_next(ctx)  # сразу воспроизводим песню, если ничего не играет
            await ctx.send(f'Сейчас играет: {player.title}')
        else:
            await ctx.send(f'Добавлено в очередь: {player.title}')
    except Exception as e:
        await ctx.send(f'Не удалось воспроизвести: {e}')

async def play_next(ctx):
    if music_queue.peek():
        next_song = music_queue.pop()  # берем следующую песню из очереди
        ctx.guild.voice_client.play(next_song, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
        await ctx.send(f'Сейчас играет: {next_song.title}')
    else:
        await ctx.send("Очередь пуста.")

@bot.slash_command()
async def skip(ctx: disnake.ApplicationCommandInteraction):
    """Пропустить текущую песню"""
    if ctx.guild.voice_client and ctx.guild.voice_client.is_playing():
        ctx.guild.voice_client.stop()  # просто останавливаем текущую песню
        await ctx.send("Текущая песня пропущена.")

@bot.slash_command()
async def queue(ctx: disnake.ApplicationCommandInteraction):
    """Показать очередь"""
    if len(music_queue) == 0:
        await ctx.send("Очередь пуста.")
    else:
        queue_list = '\n'.join([f"{i + 1}. {song.title}" for i, song in enumerate(music_queue.queue)])
        await ctx.send(f"Очередь:\n{queue_list}")

@bot.slash_command()
async def pause(ctx: disnake.ApplicationCommandInteraction):
    """Пауза музыки"""
    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await ctx.send("Музыка на паузе.")
    else:
        await ctx.send("Музыка сейчас не играет.")

@bot.slash_command()
async def resume(ctx: disnake.ApplicationCommandInteraction):
    """Возобновить музыку"""
    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await ctx.send("Музыка продолжена.")
    else:
        await ctx.send("Музыка не была приостановлена.")

@bot.slash_command()
async def stop(ctx: disnake.ApplicationCommandInteraction):
    """Остановить музыку"""
    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        music_queue.clear()  # очищаем очередь, когда останавливаем воспроизведение
        await ctx.send("Музыка остановлена и очередь очищена.")
    else:
        await ctx.send("Сейчас нет активного воспроизведения.")

@bot.event
async def on_ready():
    print(f'{bot.user} подключен и готов!')

@play.before_invoke
async def ensure_voice(interaction: disnake.ApplicationCommandInteraction):
    """Убедиться, что бот в голосовом канале"""
    if interaction.guild.voice_client is None:
        if interaction.author.voice:
            await interaction.author.voice.channel.connect()
        else:
            await interaction.send("Вы должны быть в голосовом канале для использования этой команды.")
            raise commands.CommandError("Пользователь не в голосовом канале.")
    elif interaction.guild.voice_client.is_playing():
        pass  # Позволяем воспроизводить несколько песен в очереди

bot.run(TOKEN)

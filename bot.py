import os
import time
import asyncio
import logging
from pathlib import Path

import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

XKIRO_API_KEY = os.environ["XKIRO_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
ADMIN_ID = int(os.environ["ADMIN_ID"])

IMAGE_MODEL = os.getenv(
    "IMAGE_MODEL",
    "sensenova/sensenova-u1.5-lite"
)

INTERVAL_MINUTES = int(
    os.getenv("INTERVAL_MINUTES", "30")
)

AUTO_START = os.getenv(
    "AUTO_START", "true"
).lower() == "true"

GENERATE_URL = "https://api.xkiro.com/v1/images/generations"
STATUS_URL = "https://api.xkiro.com/v1/images/generations/{id}"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

log = logging.getLogger("wallpaper-bot")

running = AUTO_START
last_post = None
last_error = None

PROMPTS = [
    "A breathtaking futuristic city floating above the clouds at sunset, cinematic realistic wallpaper, ultra detailed, dramatic lighting, vertical composition, no text",

    "A magical forest with a crystal lake, glowing fireflies and mountains, cinematic realistic wallpaper, ultra detailed, vertical composition, no text",

    "A peaceful tropical island with crystal clear water and a small wooden boat during golden sunset, photorealistic cinematic wallpaper, vertical composition, no text",

    "An ancient castle on a mountain above the clouds under moonlight, cinematic fantasy wallpaper, highly detailed, vertical composition, no text",

    "A tiny futuristic village built inside a giant tree, miniature world, glowing lights, cinematic realism, highly detailed, vertical composition, no text",

    "A spectacular waterfall hidden inside a lush jungle, morning mist and sun rays, photorealistic cinematic wallpaper, vertical composition, no text",

    "A futuristic train traveling through snowy mountains at night, glowing windows, stars and aurora, cinematic wallpaper, vertical composition, no text",

    "A beautiful desert oasis under a star-filled night sky, moonlight and palm trees, cinematic wallpaper, ultra detailed, vertical composition, no text"
]

prompt_index = 0


def admin_only(update: Update):
    return (
        update.effective_user
        and update.effective_user.id == ADMIN_ID
    )


def generate_image(prompt):

    headers = {
        "Authorization": f"Bearer {XKIRO_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1536"
    }

    r = requests.post(
        GENERATE_URL,
        headers=headers,
        json=payload,
        timeout=90
    )

    r.raise_for_status()

    data = r.json()

    job_id = data.get("id")

    if not job_id:
        raise Exception(
            f"No job ID returned: {data}"
        )

    log.info("Job ID: %s", job_id)

    for _ in range(72):

        time.sleep(5)

        url = STATUS_URL.format(id=job_id)

        r = requests.get(
            url,
            headers={
                "Authorization":
                f"Bearer {XKIRO_API_KEY}"
            },
            timeout=45
        )

        r.raise_for_status()

        job = r.json()

        status = job.get("status")

        log.info(
            "Generation status: %s",
            status
        )

        if status == "succeeded":

            items = job.get("data", [])

            if not items:
                raise Exception(
                    "No image returned."
                )

            image_url = items[0].get("url")

            if not image_url:
                raise Exception(
                    "Image URL missing."
                )

            image = requests.get(
                image_url,
                timeout=120
            )

            image.raise_for_status()

            path = Path(
                "/tmp/wallpaper.jpg"
            )

            path.write_bytes(
                image.content
            )

            return path

        if status in [
            "failed",
            "blocked",
            "cancelled"
        ]:
            raise Exception(
                f"Generation {status}: {job}"
            )

    raise Exception(
        "Image generation timed out."
    )


def upload_to_channel(path):

    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    )

    with open(path, "rb") as photo:

        r = requests.post(
            url,
            data={
                "chat_id": CHANNEL_ID
            },
            files={
                "photo": photo
            },
            timeout=120
        )

    r.raise_for_status()

    result = r.json()

    if not result.get("ok"):
        raise Exception(
            f"Telegram error: {result}"
        )


def generate_and_post():

    global prompt_index
    global last_post
    global last_error

    prompt = PROMPTS[
        prompt_index % len(PROMPTS)
    ]

    prompt_index += 1

    log.info(
        "Generating: %s",
        prompt
    )

    path = None

    try:

        path = generate_image(
            prompt
        )

        upload_to_channel(
            path
        )

        last_post = time.strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )

        last_error = None

        log.info(
            "Wallpaper posted successfully."
        )

    except Exception as e:

        last_error = str(e)

        log.exception(
            "Post failed"
        )

        raise

    finally:

        if path:

            try:
                path.unlink(
                    missing_ok=True
                )
            except:
                pass


async def post_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not admin_only(update):
        return

    await update.message.reply_text(
        "🖼️ Generating wallpaper..."
    )

    try:

        await asyncio.to_thread(
            generate_and_post
        )

        await update.message.reply_text(
            "✅ Wallpaper posted."
        )

    except Exception as e:

        await update.message.reply_text(
            f"❌ Error:\n{str(e)[:3000]}"
        )


async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    global running

    if not admin_only(update):
        return

    running = True

    await update.message.reply_text(
        f"🟢 Auto posting ON\n"
        f"⏱️ Every {INTERVAL_MINUTES} minutes"
    )


async def stop_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    global running

    if not admin_only(update):
        return

    running = False

    await update.message.reply_text(
        "🔴 Auto posting OFF"
    )


async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not admin_only(update):
        return

    state = (
        "🟢 ON"
        if running
        else "🔴 OFF"
    )

    await update.message.reply_text(
        f"Status: {state}\n"
        f"Interval: {INTERVAL_MINUTES} min\n"
        f"Last post: {last_post or 'None'}\n"
        f"Last error: "
        f"{last_error or 'None'}"
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not admin_only(update):
        return

    await update.message.reply_text(
        "🖼️ Wallpaper World Bot\n\n"
        "/post - Generate now\n"
        "/start - Start auto posting\n"
        "/stop - Stop auto posting\n"
        "/status - Bot status\n"
        "/help - Commands\n\n"
        "Posts contain image only."
    )


async def scheduler():

    global running

    await asyncio.sleep(20)

    while True:

        if running:

            try:

                log.info(
                    "Automatic generation started."
                )

                await asyncio.to_thread(
                    generate_and_post
                )

            except Exception as e:

                log.error(
                    "Auto post error: %s",
                    e
                )

        await asyncio.sleep(
            INTERVAL_MINUTES * 60
        )


async def startup(
    application
):

    application.create_task(
        scheduler()
    )


def main():

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(startup)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "post",
            post_command
        )
    )

    app.add_handler(
        CommandHandler(
            "start",
            start_command
        )
    )

    app.add_handler(
        CommandHandler(
            "stop",
            stop_command
        )
    )

    app.add_handler(
        CommandHandler(
            "status",
            status_command
        )
    )

    app.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    log.info(
        "Wallpaper World Bot started."
    )

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
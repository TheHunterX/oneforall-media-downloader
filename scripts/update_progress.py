import os
import sys
import json
import urllib.request

def update_progress():
    if len(sys.argv) < 5:
        print("[Progress] Usage: update_progress.py <chat_id> <message_id> <percent> <status_text>")
        return

    chat_id = sys.argv[1].strip()
    msg_id = sys.argv[2].strip()
    percent_str = sys.argv[3].strip()
    status_text = sys.argv[4].strip()

    if not chat_id or not msg_id or not percent_str.isdigit():
        print("[Progress] Invalid args, skipping.")
        return

    percent = int(percent_str)
    token = os.environ.get("TGCLOUD_TOKEN", "").strip()
    if not token:
        return
    app_id = token.split(":")[0] if ":" in token else "app9005060404"

    js_code = """
import { api } from 'sdk';

function renderProgressBar(percent) {
  const totalBars = 12;
  const filled = Math.min(totalBars, Math.max(0, Math.round((percent / 100) * totalBars)));
  return '█'.repeat(filled) + '░'.repeat(totalBars - filled);
}

export default async function(args) {
    try {
        const bar = renderProgressBar(args.percent);
        const caption = 
            '⏳ <b>Downloading Media Engine...</b>\\n\\n' +
            '<code>[' + bar + ']</code> <b>' + args.percent + '%</b>\\n' +
            '⚡ <b>Status:</b> ' + args.status + '\\n\\n' +
            '📡 @OneForAllHub';

        try {
            await api.editMessageCaption({
                chat_id: args.chat_id,
                message_id: args.message_id,
                parse_mode: 'HTML',
                caption: caption
            });
        } catch (_) {
            await api.editMessageText({
                chat_id: args.chat_id,
                message_id: args.message_id,
                parse_mode: 'HTML',
                text: caption
            });
        }
        return { ok: true };
    } catch (e) {
        return { ok: false, error: e.message };
    }
}
"""
    payload = {
        "module": "endpoints/update_progress",
        "sources": {"endpoints/update_progress": js_code},
        "args": {
            "chat_id": int(chat_id),
            "message_id": int(msg_id),
            "percent": percent,
            "status": status_text
        }
    }
    try:
        req = urllib.request.Request(
            f"https://cloud.telegram.org/{app_id}/manage/run",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[Progress] Updated message {msg_id} in chat {chat_id} to {percent}%: {status_text}")
    except Exception as e:
        print(f"[Progress] Update non-fatal note: {e}")

if __name__ == "__main__":
    update_progress()

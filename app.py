import os
import anthropic
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

app = Flask(__name__)

# ดึง config จาก Environment Variables
configuration = Configuration(access_token=os.environ["LINE_TOKEN"])
handler = WebhookHandler(os.environ["LINE_SECRET"])
claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# เก็บประวัติการสนทนาของแต่ละ user (key = user_id)
conversation_history = {}

SYSTEM_PROMPT = """คุณคือ HealthBot AI ผู้ช่วยด้านสุขภาพภาษาไทย

หน้าที่ของคุณ:
1. ให้ข้อมูลอาการและวิธีดูแลตนเองเบื้องต้น
2. บอกเมื่อไหร่ควรไปพบแพทย์หรือโรงพยาบาล
3. แนะนำการดูแลสุขภาพและป้องกันโรค
4. ข้อมูลยาสามัญประจำบ้านเบื้องต้น
5. ปฐมพยาบาลเบื้องต้น

กฎสำคัญ:
- ตอบภาษาไทยเสมอ กระชับ ชัดเจน เข้าใจง่าย
- ถ้าอาการฉุกเฉิน (หัวใจวาย สมองขาดเลือด แพ้รุนแรง) ให้บอกโทร 1669 ทันที
- ใช้ bullet points ให้อ่านง่าย
- เน้น "เมื่อไหร่ควรพบแพทย์" ในทุกคำตอบ
- ไม่วินิจฉัยโรค แต่ให้ข้อมูลทั่วไปและแนะนำทิศทาง
- ใช้ภาษาอบอุ่น เป็นมิตร
- ตอบสั้นกระชับ ไม่เกิน 200 คำ เหมาะกับ LINE chat
- ท้ายข้อความให้ใส่ข้อความว่า ⚠️ ข้อมูลนี้เป็นเบื้องต้นเท่านั้น ไม่ใช่การวินิจฉัยทางการแพทย์"""


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    user_msg = event.message.text

    # สร้าง history ของ user ถ้ายังไม่มี
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    # เพิ่มข้อความ user เข้า history
    conversation_history[user_id].append({
        "role": "user",
        "content": user_msg
    })

    # จำกัด history ไว้ 10 รอบ เพื่อไม่ให้ token เกิน
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]

    # เรียก Claude API
    response = claude.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=conversation_history[user_id]
    )

    reply_text = response.content[0].text

    # เพิ่มคำตอบ bot เข้า history
    conversation_history[user_id].append({
        "role": "assistant",
        "content": reply_text
    })

    # ส่งคำตอบกลับ LINE
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)]
            )
        )


@app.route("/", methods=["GET"])
def index():
    return "HealthBot AI is running! 🩺"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

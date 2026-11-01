import asyncio
import base64
import io
import os
import random
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile
from playwright.async_api import async_playwright
import barcode
from barcode.writer import ImageWriter

BOT_TOKEN = "9176690291:AAHVV0RjsNzvA1ePYot63S6C5KNaUJZJYoY"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class OrderStates(StatesGroup):
    waiting_for_date = State()
    waiting_for_sender_company = State()
    waiting_for_company = State()
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_address = State()
    waiting_for_item = State()
    waiting_for_weight = State()
    waiting_for_price = State()
    waiting_for_order_id = State()
    waiting_for_waybill_num = State()

def generate_barcode_base64(code_text: str) -> str:
    CODE128 = barcode.get_barcode_class('code128')
    rv = io.BytesIO()
    CODE128(code_text, writer=ImageWriter()).write(rv, options={'write_text': False, 'module_height': 8.0, 'module_width': 0.6})
    return base64.b64encode(rv.getvalue()).decode()

async def render_pdf(data: dict) -> str:
    with open("index.html", "r", encoding="utf-8") as f:
        html_content = f.read()

    for key, value in data.items():
        if key == "barcode_b64":
            continue
        pattern = r"\{\{\s*" + key + r"\s*\}\}"
        html_content = re.sub(pattern, str(value), html_content)

    html_content = re.sub(r'\{\{\s*barcode_b64\s*\}\}', data.get("barcode_b64", ""), html_content)
    html_content = html_content.replace("{% if barcode_b64 %}", "").replace("{% endif %}", "")

    output_html = "temp_cdek.html"
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    pdf_filename = f"cdek_{data.get('waybill_num', '10')}.pdf"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(f"file://{os.path.abspath(output_html)}")
        await page.pdf(path=pdf_filename, format="A4", print_background=True)
        await browser.close()

    if os.path.exists(output_html):
        os.remove(output_html)

    return pdf_filename

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Здорово! Начинаем оформление накладной СДЭК.\n\nВведи **дату отправки** (например, 01.12.2024):")
    await state.set_state(OrderStates.waiting_for_date)

@dp.message(OrderStates.waiting_for_date)
async def process_date(message: types.Message, state: FSMContext):
    await state.update_data(date=message.text)
    await message.answer("Напиши **название компании отправителя**:")
    await state.set_state(OrderStates.waiting_for_sender_company)

@dp.message(OrderStates.waiting_for_sender_company)
async def process_sender_company(message: types.Message, state: FSMContext):
    await state.update_data(sender_company=message.text)
    await message.answer("Напиши **название компании получателя** (или прочерк):")
    await state.set_state(OrderStates.waiting_for_company)

@dp.message(OrderStates.waiting_for_company)
async def process_company(message: types.Message, state: FSMContext):
    await state.update_data(recipient_company=message.text)
    await message.answer("Введи **ФИО получателя**:")
    await state.set_state(OrderStates.waiting_for_name)

@dp.message(OrderStates.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(recipient_name=message.text)
    await message.answer("Введи **номер телефона** получателя:")
    await state.set_state(OrderStates.waiting_for_phone)

@dp.message(OrderStates.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(recipient_phone=message.text)
    await message.answer("Введи **город и адрес** доставки:")
    await state.set_state(OrderStates.waiting_for_address)

@dp.message(OrderStates.waiting_for_address)
async def process_address(message: types.Message, state: FSMContext):
    await state.update_data(recipient_address=message.text)
    await message.answer("Опиши **название товара**:")
    await state.set_state(OrderStates.waiting_for_item)

@dp.message(OrderStates.waiting_for_item)
async def process_item(message: types.Message, state: FSMContext):
    await state.update_data(item_desc=message.text)
    await message.answer("Введи **вес товара** (например, 0.5 кг):")
    await state.set_state(OrderStates.waiting_for_weight)

@dp.message(OrderStates.waiting_for_weight)
async def process_weight(message: types.Message, state: FSMContext):
    await state.update_data(item_weight=message.text)
    await message.answer("Введи **стоимость / объявленную цену** (только цифру, например 12500):")
    await state.set_state(OrderStates.waiting_for_price)

@dp.message(OrderStates.waiting_for_price)
async def process_price(message: types.Message, state: FSMContext):
    await state.update_data(declared_price=message.text)
    await message.answer("Введи **номер заказа** (должен начинаться с **285** и содержать ровно **13 цифр**):")
    await state.set_state(OrderStates.waiting_for_order_id)

@dp.message(OrderStates.waiting_for_order_id)
async def process_order_id(message: types.Message, state: FSMContext):
    order_id = message.text.strip()
    if not order_id.startswith("285") or len(order_id) != 13 or not order_id.isdigit():
        await message.answer("❌ Ошибка! Номер заказа должен начинаться с **285** и состоять ровно из **13 цифр**. Попробуй еще раз:")
        return

    await state.update_data(order_id=order_id)
    await state.update_data(barcode_b64=generate_barcode_base64(order_id))
    
    await message.answer("Введи **номер накладной** (11 цифр под верхним штрихкодом):")
    await state.set_state(OrderStates.waiting_for_waybill_num)

@dp.message(OrderStates.waiting_for_waybill_num)
async def process_waybill_num(message: types.Message, state: FSMContext):
    waybill_num = message.text.strip()
    await state.update_data(waybill_num=waybill_num)

    data = await state.get_data()

    await message.answer("⏳ Генерирую накладную СДЭК, секунду...")

    try:
        pdf_path = await render_pdf(data)
        document = FSInputFile(pdf_path)
        await message.answer_document(document, caption=f"✅ Готово! Накладная №{waybill_num}")
        
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
    except Exception as e:
        await message.answer(f"❌ Произошла ошибка при генерации PDF: {e}")

    await state.clear()

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

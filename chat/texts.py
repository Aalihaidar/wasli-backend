"""Every sentence the bot says, in Arabic and English.

The backend writes all customer-facing text; the assistant only understands. A text is chosen by
the conversation's locale and filled with names that come from the restaurant's own menu. The
names are data (they are never run through ``format`` themselves), so a menu item called
``{x}`` cannot break a sentence.
"""

from core.locales import Locale

_TEXTS: dict[str, dict[str, str]] = {
    "welcome": {
        "en": "Welcome to {restaurant}.",
        "ar": "أهلاً بك في {restaurant}.",
    },
    "what_to_order": {
        "en": "What would you like to order?",
        "ar": "ماذا تريد أن تطلب؟",
    },
    "summary_question": {
        "en": "Do you confirm the order or do you want to edit it?",
        "ar": "هل تؤكد الطلب أم تريد تعديله؟",
    },
    "edit_prompt": {
        "en": "Tell me what you would like to change: add, remove or change an item.",
        "ar": "قل لي ما الذي تريد تغييره: إضافة صنف أو حذفه أو تعديله.",
    },
    "empty_order": {
        "en": "Your order is empty. What would you like to order?",
        "ar": "طلبك فارغ. ماذا تريد أن تطلب؟",
    },
    "cleared": {
        "en": "I cleared your order. What would you like to order?",
        "ar": "لقد أفرغت طلبك. ماذا تريد أن تطلب؟",
    },
    "restarted": {
        "en": "Let's start again. What would you like to order?",
        "ar": "لنبدأ من جديد. ماذا تريد أن تطلب؟",
    },
    "not_understood": {
        "en": "Sorry, I did not understand that. Please write what you would like to order.",
        "ar": "عذراً، لم أفهم ذلك. اكتب ما تريد أن تطلبه.",
    },
    "unmatched": {
        "en": "I could not find this on the menu: {items}.",
        "ar": "لم أجد هذا في القائمة: {items}.",
    },
    "unavailable": {
        "en": "Not available right now: {items}.",
        "ar": "غير متوفر حالياً: {items}.",
    },
    "too_many_lines": {
        "en": "An order can have at most {limit} different items.",
        "ar": "يمكن أن يحتوي الطلب على {limit} أصناف مختلفة كحد أقصى.",
    },
    "choose_item": {
        "en": "Which one do you mean by “{mention}”?",
        "ar": "أي واحد تقصد بـ «{mention}»؟",
    },
    "choose_item_plain": {
        "en": "Which one do you mean?",
        "ar": "أي واحد تقصد؟",
    },
    "choose_option": {
        "en": "Which {group} would you like for {item}?",
        "ar": "أي {group} تريد لـ {item}؟",
    },
    "stale_choice": {
        "en": "That choice is not available any more. Please tell me what you want.",
        "ar": "هذا الخيار لم يعد متاحاً. أخبرني ماذا تريد.",
    },
    "assistant_down": {
        "en": "I cannot understand typed or spoken orders right now. Please pick your items from the menu.",
        "ar": "لا أستطيع فهم الطلبات المكتوبة أو المنطوقة الآن. اختر أصنافك من القائمة.",
    },
    "could_not_hear": {
        "en": "Sorry, I could not hear that. Please say it again.",
        "ar": "عذراً، لم أسمع ذلك جيداً. من فضلك قلها مرة أخرى.",
    },
    "voice_unavailable": {
        "en": "I cannot understand voice messages right now. Please type your order or pick your items from the menu.",
        "ar": "لا أستطيع فهم الرسائل الصوتية الآن. اكتب طلبك أو اختر أصنافك من القائمة.",
    },
    "restaurant_unavailable": {
        "en": "This restaurant is not taking orders right now.",
        "ar": "هذا المطعم لا يستقبل الطلبات الآن.",
    },
    "car_question": {
        "en": (
            "Where are you parked? In one message, tell me the parking name and where your car "
            "is, the car number, the model and the colour. The restaurant may reject the order "
            "if it does not know where you are."
        ),
        "ar": (
            "أين أوقفت سيارتك؟ في رسالة واحدة، أخبرني باسم الموقف ومكان سيارتك، ورقم السيارة، "
            "وموديلها ولونها. قد يرفض المطعم الطلب إذا لم يعرف مكانك."
        ),
    },
    "car_still_need": {
        "en": "Thank you. I still need {items}.",
        "ar": "شكراً. ما زلت بحاجة إلى {items}.",
    },
    "car_not_caught": {
        "en": "I did not catch that. I still need {items}.",
        "ar": "لم أفهم ذلك. ما زلت بحاجة إلى {items}.",
    },
    "car_show": {
        "en": "This is what I have:\n{values}\nTell me what to change.",
        "ar": "هذا ما لدي:\n{values}\nأخبرني ما الذي تريد تغييره.",
    },
    "car_no_change": {
        "en": "I did not catch a change. Tell me what to change.",
        "ar": "لم ألتقط أي تغيير. أخبرني ما الذي تريد تغييره.",
    },
    "car_fallback_intro": {
        "en": "I cannot read free answers right now, so I will ask you one thing at a time.",
        "ar": "لا أستطيع قراءة الإجابات الحرة الآن، لذلك سأسألك عن شيء واحد في كل مرة.",
    },
    "car_voice_unavailable": {
        "en": "I cannot understand voice messages right now. Please type your answer.",
        "ar": "لا أستطيع فهم الرسائل الصوتية الآن. اكتب إجابتك من فضلك.",
    },
    "car_ask_parking_note": {
        "en": (
            "Where are you parked? Type the parking name and where your car is. The restaurant "
            "may reject the order if it does not know where you are."
        ),
        "ar": (
            "أين أوقفت سيارتك؟ اكتب اسم الموقف ومكان سيارتك. قد يرفض المطعم الطلب إذا لم يعرف مكانك."
        ),
    },
    "car_ask_plate": {"en": "What is the car number?", "ar": "ما رقم السيارة؟"},
    "car_ask_model": {"en": "What is the car model?", "ar": "ما موديل السيارة؟"},
    "car_ask_colour": {"en": "What is the car colour?", "ar": "ما لون السيارة؟"},
    "car_current": {"en": "Now: {value}", "ar": "الحالي: {value}"},
    "car_invalid": {
        "en": "That does not fit: {item} must be between {low} and {high} characters. Please try again.",
        "ar": "هذه الإجابة غير مناسبة: يجب أن يكون {item} بين {low} و{high} حرفاً. حاول مرة أخرى.",
    },
    "car_label_parking_note": {
        "en": "where your car is (the parking name and the spot)",
        "ar": "مكان سيارتك (اسم الموقف والمكان)",
    },
    "car_label_plate": {"en": "the car number", "ar": "رقم السيارة"},
    "car_label_model": {"en": "the car model", "ar": "موديل السيارة"},
    "car_label_colour": {"en": "the car colour", "ar": "لون السيارة"},
    "car_value_parking_note": {"en": "Parking", "ar": "الموقف"},
    "car_value_plate": {"en": "Number", "ar": "الرقم"},
    "car_value_model": {"en": "Model", "ar": "الموديل"},
    "car_value_colour": {"en": "Colour", "ar": "اللون"},
    "note_question": {
        "en": "Any note for the order? You can skip.",
        "ar": "هل لديك ملاحظة على الطلب؟ يمكنك التخطي.",
    },
    "note_edit": {
        "en": "Your note is: “{note}”. Tell me the new note, or tap Keep to leave it.",
        "ar": "ملاحظتك هي: «{note}». اكتب الملاحظة الجديدة، أو اضغط إبقاء لتركها.",
    },
    "note_too_long": {
        "en": "A note can have at most {limit} characters. Please make it shorter.",
        "ar": "يمكن أن تحتوي الملاحظة على {limit} حرفاً كحد أقصى. اجعلها أقصر من فضلك.",
    },
    "review_question": {
        "en": "Shall I send the order to the restaurant?",
        "ar": "هل أرسل الطلب إلى المطعم؟",
    },
    "review_edit_prompt": {
        "en": "What would you like to edit?",
        "ar": "ماذا تريد أن تعدّل؟",
    },
    "use_buttons": {
        "en": "I cannot read free text right now. Please use the buttons.",
        "ar": "لا أستطيع قراءة النص الحر الآن. استخدم الأزرار من فضلك.",
    },
    "placed": {
        "en": "Your order #{number} was sent. Waiting for the restaurant to confirm.",
        "ar": "تم إرسال طلبك رقم {number}. بانتظار تأكيد المطعم.",
    },
    # The restaurant's answer, posted into the chat as the `result` message.
    "result_accepted": {
        "en": "Good news: your order #{number} was accepted. It will be ready in about {minutes} minutes.",
        "ar": "أخبار سارة: تم قبول طلبك رقم {number}. سيكون جاهزاً خلال {minutes} دقيقة تقريباً.",
    },
    "result_rejected": {
        "en": "Sorry, the restaurant could not accept your order #{number}. {reason}",
        "ar": "عذراً، لم يتمكن المطعم من قبول طلبك رقم {number}. {reason}",
    },
    "reject_item_unavailable": {
        "en": "Part of the order is finished or unavailable.",
        "ar": "جزء من الطلب انتهى أو غير متوفر.",
    },
    "reject_too_busy": {
        "en": "The restaurant is too busy right now.",
        "ar": "المطعم مشغول جداً الآن.",
    },
    "reject_closing_soon": {
        "en": "The restaurant is closing soon.",
        "ar": "المطعم سيغلق قريباً.",
    },
    "reject_too_far": {
        "en": "You are too far from the restaurant.",
        "ar": "أنت بعيد جداً عن المطعم.",
    },
    "reject_location_unclear": {
        "en": "The restaurant could not tell where you are.",
        "ar": "لم يتمكن المطعم من تحديد مكانك.",
    },
    "reject_other": {
        "en": "The restaurant says:",
        "ar": "يقول المطعم:",
    },
    "outside_service_distance": {
        "en": "Sorry, you seem to be outside the area this restaurant serves. Please move closer and send the order again.",
        "ar": "عذراً، يبدو أنك خارج المنطقة التي يخدمها هذا المطعم. اقترب وأرسل الطلب مرة أخرى.",
    },
    "yes_send_label": {"en": "Yes, send", "ar": "نعم، أرسل"},
    "keep_label": {"en": "Keep", "ar": "إبقاء"},
    "edit_order_label": {"en": "Order", "ar": "الطلب"},
    "edit_car_label": {"en": "Car and parking", "ar": "السيارة والموقف"},
    "edit_note_label": {"en": "Note", "ar": "الملاحظة"},
    # The labels of buttons, also the text kept for a customer's tap.
    "confirm_label": {"en": "Confirm", "ar": "تأكيد"},
    "edit_label": {"en": "Edit", "ar": "تعديل"},
    "skip_label": {"en": "Skip", "ar": "تخطي"},
    "restart_label": {"en": "Start again", "ar": "البدء من جديد"},
    "locale_label": {"en": "English", "ar": "العربية"},
    "picked_items": {
        "en": "Items picked from the menu",
        "ar": "أصناف اخترتها من القائمة",
    },
}


def say(key: str, locale: str, **names: object) -> str:
    """The text ``key`` in ``locale``, with ``names`` put into it."""
    texts = _TEXTS[key]
    template = texts.get(locale) or texts[Locale.EN.value]
    return template.format(**{name: str(value) for name, value in names.items()})


def pick(english: str, arabic: str, locale: str) -> str:
    """A name in the conversation's language (the Arabic one has already fallen back to the
    English one when the restaurant has none)."""
    return arabic if locale == Locale.AR.value else english

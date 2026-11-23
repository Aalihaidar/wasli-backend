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

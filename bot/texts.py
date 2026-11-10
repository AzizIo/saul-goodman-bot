"""Тексты и форматирование Saul Goodman ⚖️."""
from __future__ import annotations

from decimal import Decimal

import config


def money(cents: int) -> str:
    """150 -> $1.50"""
    return f"{config.CURRENCY}{Decimal(cents) / 100:.2f}"


def progress_bar(success: int, threshold: int, width: int = 10) -> str:
    if threshold <= 0:
        return "🟩" * width
    filled = int((success / threshold) * width)
    filled = max(0, min(width, filled))
    return "🟩" * filled + "⬜" * (width - filled)


def rank_for(success: int) -> dict:
    current = config.RANK_LEVELS[0]
    for rank in config.RANK_LEVELS:
        if success >= rank["threshold"]:
            current = rank
        else:
            break
    return current


def next_rank(success: int) -> dict | None:
    for rank in config.RANK_LEVELS:
        if success < rank["threshold"]:
            return rank
    return None


def rank_bonus_cents(success: int) -> int:
    return int(rank_for(success)["bonus_cents"])


# --- Экраны ----------------------------------------------------------------


def subscription_required() -> str:
    return (
        "⚖️ <b>Стоп, адвокат.</b>\n\n"
        "Чтобы войти в кабинет, нужно быть в нашем канале. "
        "Подпишись и жми «Проверить» — я не люблю бюрократию, но правила есть правила."
    )


def pending_review() -> str:
    return (
        "🕓 <b>Заявка на столе у администратора</b>\n\n"
        "Я уже передал твою кандидатуру. Как только доступ подтвердят — "
        "вернись и жми /start, кабинет откроется."
    )


def banned() -> str:
    return (
        "🚫 <b>Доступ закрыт</b>\n\n"
        "Твоя учётная запись заблокирована. Если считаешь, что это ошибка — "
        "напиши в поддержку, разберёмся по-человечески."
    )


def main_menu(name: str | None = None) -> str:
    who = f", <b>{name}</b>" if name else ""
    return (
        f"⚖️ <b>Saul Goodman на связи{who}</b>\n\n"
        "Твой кабинет открыт. Сдавай QR, следи за сделками, выводи деньги.\n\n"
        "«<i>Better Call Saul</i>» — но здесь всё по-честному."
    )


def choose_operator() -> str:
    return (
        "📱 <b>Выбери оператора</b>\n\n"
        "🟢 — приём открыт, 🔴 — приём закрыт.\n"
        "Цена указана за успешно засчитанную сдачу."
    )


def ask_qr(operator: str, price_cents: int) -> str:
    return (
        f"📷 <b>{operator}</b> — {money(price_cents)} за сдачу\n\n"
        "Отправь <b>фото QR/eSIM</b> и в подписи укажи <b>номер телефона</b>.\n"
        "Без номера в подписи заказ не приму — это не придирка, это проверка."
    )


def qr_bad_caption() -> str:
    return (
        "⚠️ <b>Не вижу номер</b>\n\n"
        "Отправь фото ещё раз и обязательно добавь номер телефона в подпись "
        "(например: <code>+79001234567</code>)."
    )


def qr_wrong_content() -> str:
    return "⚠️ Нужно именно <b>фото</b> QR/eSIM, а не текст или файл. Пробуй ещё."


def order_accepted(order_id: int, price_cents: int) -> str:
    return (
        f"✅ <b>Принято, заказ #{order_id}, сумма {money(price_cents)}</b>\n\n"
        "Проверю и вернусь с результатом. Пока можешь глянуть профиль."
    )


def operator_closed(operator: str) -> str:
    return f"🔴 <b>{operator}</b> — приём закрыт. Выбери другого оператора."


def support_prompt() -> str:
    return (
        "🆘 <b>Поддержка</b>\n\n"
        "Опиши проблему одним сообщением — оно уйдёт администратору с обратной связью. "
        "Не тяни: чем точнее вопрос, тем быстрее ответ."
    )


def support_sent(ticket_id: int) -> str:
    return (
        f"📨 <b>Обращение #{ticket_id} отправлено</b>\n\n"
        "Ответ придёт сюда же. Спасибо за терпение, адвокат."
    )


def withdraw_prompt(min_cents: int) -> str:
    return (
        "💳 <b>Вывод средств</b>\n\n"
        f"Минимальная сумма — {money(min_cents)}.\n\n"
        "Отправь одним сообщением <b>сеть и адрес кошелька</b>:\n"
        "например, <code>USDT BEP20 0x...</code> или <code>USDT TRC20 T...</code>\n\n"
        "Или просто адрес — тогда по умолчанию возьму <b>USDT TRC20</b>."
    )


def withdraw_no_funds(min_cents: int, available_cents: int) -> str:
    return (
        f"📉 <b>Не хватает средств</b>\n\n"
        f"Доступно: {money(available_cents)}, минимум: {money(min_cents)}.\n"
        "Сдай ещё пару QR — и дело в шляпе."
    )


def withdraw_bad_wallet() -> str:
    return (
        "⚠️ <b>Адрес не похож на кошелёк</b>\n\n"
        "Пришли адрес ещё раз: <code>0x…</code> для BEP20 или <code>T…</code> для TRC20."
    )


def withdraw_created(wid: int, amount_cents: int, network: str, wallet: str) -> str:
    return (
        f"🧾 <b>Заявка на вывод #{wid}</b>\n\n"
        f"Сумма: <b>{money(amount_cents)}</b>\n"
        f"Сеть: <b>{network}</b>\n"
        f"Кошелёк: <code>{wallet}</code>\n\n"
        "Средства зарезервированы. Администратор переведёт вручную и пришлёт чек."
    )


def profile(
    user_id: int,
    balance_cents: int,
    available_cents: int,
    stats: dict[str, int],
    operators: list,
) -> str:
    success = stats.get("success", 0)
    rank = rank_for(success)
    nxt = next_rank(success)
    lines = [
        "📥 <b>Кабинет продавца</b>",
        "",
        "✦ <b>Сводка</b>",
        "",
        f"✅ Встало: {success}",
        f"⏳ В работе: {stats.get('in_progress', 0)}",
        f"⛔ Брак: {stats.get('failed', 0)}",
        f"📥 Загружено: {stats.get('total', 0)}",
        f"💵 За вставшие: {money(stats.get('earned', 0))}",
        "",
        f"💰 Баланс: <b>{money(balance_cents)}</b> · доступно: <b>{money(available_cents)}</b>",
        f"🎖 Ранг: <b>{rank['name']}</b>",
    ]
    if operators:
        lines += ["", "✦ <b>Операторы</b>", ""]
        for row in operators:
            lines.append(f"{row['operator']}: ✅ {row['s'] or 0} ⏳ {row['p'] or 0} ⛔ {row['f'] or 0}")
    lines += ["", "✦ <b>До следующего ранга:</b>", ""]
    if nxt:
        left = nxt["threshold"] - success
        lines.append(progress_bar(success, nxt["threshold"]))
        lines.append("")
        lines.append(f"До {nxt['name']} осталось {left} сдач.")
    else:
        lines.append(progress_bar(1, 1))
        lines.append("")
        lines.append("Максимальный ранг. Ты — дон этого района. 🏆")
    lines += ["", f"🆔 ID: <code>{user_id}</code>"]
    return "\n".join(lines)


def statistics(stats_24h: dict[str, int], operators: list, total_failed: int, reasons: list) -> str:
    lines = [
        "📊 <b>Статистика</b>",
        "",
        "✦ <b>За последние 24 часа</b>",
        "",
        f"📥 Всего: {stats_24h.get('total', 0)}",
        f"✅ Встало: {stats_24h.get('success', 0)}",
        f"⏳ В работе: {stats_24h.get('in_progress', 0)}",
        f"🕓 На проверке: {stats_24h.get('pending', 0)}",
        f"⛔ Брак: {stats_24h.get('failed', 0)}",
        "",
        "✦ <b>По операторам (всё время)</b>",
        "",
    ]
    if operators:
        for row in operators:
            lines.append(f"• <b>{row['operator']}</b>: ✅ {row['s'] or 0} ⏳ {row['p'] or 0} ⛔ {row['f'] or 0}")
    else:
        lines.append("<i>Пока ни одной сделки.</i>")
    lines += ["", f"⛔ <b>Всего брака: {total_failed}</b>"]
    if reasons:
        lines += ["", "✦ <b>Причины брака</b>", ""]
        for row in reasons:
            reason = (row["fail_reason"] or "").strip()
            if len(reason) > 120:
                reason = reason[:117] + "…"
            lines.append(f"• {row['operator']}: <i>{reason}</i> — {row['date'][:10]}")
    return "\n".join(lines)


# --- Админка ---------------------------------------------------------------


def admin_panel(global_stats: dict[str, int], operators_state: dict[str, bool]) -> str:
    lines = [
        "⚙️ <b>Админ-панель</b>",
        "",
        f"👥 Пользователей: <b>{global_stats['users']}</b>",
        f"📦 Заказов: <b>{global_stats['orders']}</b> (в работе: {global_stats['pending_orders']})",
        f"💳 Выплат в очереди: <b>{global_stats['payouts']}</b>",
        f"🆘 Тикетов: <b>{global_stats['tickets']}</b>",
        "",
        "✦ <b>Операторы</b>",
        "",
    ]
    for name, is_open in operators_state.items():
        lines.append(f"{'🟢' if is_open else '🔴'} {name}")
    lines += ["", "Команды: <code>/users</code>, <code>/ok_ID</code>, <code>/progress_ID</code>, "
              "<code>/no_ID причина</code>, <code>/reply_ID текст</code>, "
              "<code>/yes_ID</code>, <code>/reject_ID</code>, <code>/approve_ID</code>, <code>/ban_ID</code>."]
    return "\n".join(lines)


def admin_users(rows: list) -> str:
    lines = ["👥 <b>Пользователи</b>", ""]
    if not rows:
        lines.append("<i>Пусто. Ни одной души.</i>")
    for row in rows:
        emoji = {"active": "✅", "pending": "🕓", "banned": "🚫"}.get(row["status"], "❔")
        lines.append(
            f"{emoji} <code>{row['id']}</code> — {row['status']}, "
            f"баланс {money(row['balance'])}, доступно {money(row['available'])}"
        )
    return "\n".join(lines)
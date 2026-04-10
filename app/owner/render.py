from __future__ import annotations

from html import escape


STATUS_LABELS = {
    "pending": "Ожидает",
    "confirmed": "Подтверждена",
    "cancelled": "Отменена",
}


def csrf_input(token: str | None) -> str:
    if not token:
        return ""
    return f'<input type="hidden" name="csrf_token" value="{escape(token)}">'


def _nav_link(label: str, href: str, *, active: bool) -> str:
    class_name = "nav-link nav-link-active" if active else "nav-link"
    return f'<a class="{class_name}" href="{escape(href)}">{escape(label)}</a>'


def layout(
    *,
    title: str,
    heading: str,
    body_html: str,
    owner_email: str | None = None,
    clinic_name: str | None = None,
    csrf_token: str | None = None,
    page_key: str = "auth",
) -> str:
    if owner_email:
        nav_html = (
            '<div class="workspace-shell">'
            '<aside class="sidebar">'
            '<div class="sidebar-brand">'
            '<a class="brand" href="/owner/dashboard">AI Startup</a>'
            '<p class="sidebar-copy">Управление заявками, статусами и подключением Telegram.</p>'
            "</div>"
            '<nav class="sidebar-nav">'
            f"{_nav_link('Заявки', '/owner/dashboard', active=page_key in {'dashboard', 'booking_detail'})}"
            f"{_nav_link('Настройки', '/owner/settings', active=page_key == 'settings')}"
            "</nav>"
            '<div class="sidebar-meta">'
            '<span class="sidebar-label">Клиника</span>'
            f'<strong>{escape(clinic_name or "")}</strong>'
            f'<span class="sidebar-email">{escape(owner_email)}</span>'
            "</div>"
            '<form class="logout-form" action="/owner/logout" method="post">'
            f"{csrf_input(csrf_token)}"
            '<button class="ghost-button sidebar-button" type="submit">Выйти</button>'
            "</form>"
            "</aside>"
            '<main class="workspace-main">'
            '<header class="page-header">'
            '<div>'
            '<p class="page-kicker">Кабинет владельца</p>'
            f"<h1>{escape(heading)}</h1>"
            "</div>"
            "</header>"
            f"{body_html}"
            "</main>"
            "</div>"
        )
    else:
        nav_html = (
            '<div class="public-shell">'
            '<header class="public-header">'
            '<a class="brand brand-dark" href="/owner">AI Startup</a>'
            "</header>"
            '<main class="public-main">'
            '<section class="page-header public-page-header">'
            '<div>'
            '<p class="page-kicker">Клиника</p>'
            f"<h1>{escape(heading)}</h1>"
            "</div>"
            "</section>"
            f"{body_html}"
            "</main>"
            "</div>"
        )

    return f"""<!DOCTYPE html>
<html lang="ru">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escape(title)}</title>
    <link rel="stylesheet" href="/static/app.css">
  </head>
  <body>
    {nav_html}
  </body>
</html>
"""


def auth_card(
    *,
    title: str,
    subtitle: str,
    form_action: str,
    submit_label: str,
    email_value: str = "",
    error: str | None = None,
    footer_html: str = "",
    include_confirm_password: bool = False,
    extra_fields_html: str = "",
    csrf_token: str | None = None,
) -> str:
    error_html = ""
    if error:
        error_html = f'<div class="notice error">{escape(error)}</div>'

    confirm_field = ""
    if include_confirm_password:
        confirm_field = (
            '<label class="field">'
            '<span>Повторите пароль</span>'
            '<input type="password" name="password_confirm" autocomplete="new-password" required>'
            "</label>"
        )

    return (
        '<section class="panel auth-panel">'
        f"<h2>{escape(title)}</h2>"
        f'<p class="panel-subtitle">{escape(subtitle)}</p>'
        f"{error_html}"
        f'<form action="{escape(form_action)}" method="post" class="stack-form">'
        f"{csrf_input(csrf_token)}"
        f"{extra_fields_html}"
        '<label class="field">'
        "<span>Email</span>"
        f'<input type="email" name="email" autocomplete="email" value="{escape(email_value)}" required>'
        "</label>"
        '<label class="field">'
        "<span>Пароль</span>"
        '<input type="password" name="password" autocomplete="current-password" required>'
        "</label>"
        f"{confirm_field}"
        f'<button class="primary-button" type="submit">{escape(submit_label)}</button>'
        "</form>"
        f"{footer_html}"
        "</section>"
    )


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)

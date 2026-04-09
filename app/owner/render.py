from __future__ import annotations

from html import escape


STATUS_LABELS = {
    "pending": "Ожидает",
    "confirmed": "Подтверждена",
    "cancelled": "Отменена",
}


def layout(
    *,
    title: str,
    heading: str,
    body_html: str,
    owner_email: str | None = None,
    clinic_name: str | None = None,
) -> str:
    nav_html = ""
    if owner_email:
        nav_html = (
            '<div class="topbar">'
            '<a class="brand" href="/owner/dashboard">AI Startup</a>'
            '<div class="topbar-meta">'
            f'<span class="clinic-name">{escape(clinic_name or "")}</span>'
            f'<span class="owner-email">{escape(owner_email)}</span>'
            '<form action="/owner/logout" method="post">'
            '<button class="ghost-button" type="submit">Выйти</button>'
            "</form>"
            "</div>"
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
    <div class="page-shell">
      {nav_html}
      <main class="page-content">
        <section class="hero-card">
          <p class="eyebrow">Phase 3</p>
          <h1>{escape(heading)}</h1>
        </section>
        {body_html}
      </main>
    </div>
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

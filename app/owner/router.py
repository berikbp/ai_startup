from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass
from html import escape
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.models import Clinic, ClinicTelegramConfig, ClinicUser
from app.owner.render import auth_card, csrf_input, layout, status_label
from app.services.auth_service import (
    authenticate_owner,
    create_csrf_token,
    create_session_token,
    get_clinic_user_by_id,
    normalize_owner_email,
    validate_password,
    verify_csrf_token,
    verify_session_token,
)
from app.services.dashboard_service import get_booking_detail, list_bookings, update_booking_status
from app.services.normalization import normalize_whitespace
from app.services.onboarding_service import create_clinic_with_owner
from app.services.telegram_config_service import (
    configure_clinic_telegram_bot,
    describe_telegram_connection,
    get_clinic_telegram_config,
)


router = APIRouter(tags=["owner"])


@dataclass(slots=True)
class OwnerContext:
    clinic: Clinic
    owner: ClinicUser


@router.get("/", include_in_schema=False)
async def root_redirect() -> Response:
    return RedirectResponse(url="/owner", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/owner", include_in_schema=False)
async def owner_root(request: Request) -> Response:
    context = await _get_owner_context(request)
    return RedirectResponse(
        url="/owner/dashboard" if context is not None else "/owner/login",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/owner/register", response_class=HTMLResponse)
async def owner_register_page(request: Request) -> Response:
    context = await _get_owner_context(request)
    if context is not None:
        return _redirect("/owner/dashboard")

    csrf_token = _get_or_create_csrf_token(request)
    body = auth_card(
        title="Регистрация клиники",
        subtitle="Создайте клинику и сразу подключите первого владельца.",
        form_action="/owner/register",
        submit_label="Создать клинику",
        include_confirm_password=True,
        extra_fields_html=_registration_fields(),
        footer_html='<p class="form-footer">Если владелец уже создан, перейдите ко <a href="/owner/login">входу</a>.</p>',
        csrf_token=csrf_token,
    )
    return _html_response(
        request,
        content=layout(
            title="Регистрация клиники",
            heading="Регистрация клиники",
            body_html=body,
            csrf_token=csrf_token,
            page_key="auth",
        ),
    )


@router.post("/owner/register")
async def owner_register_submit(request: Request) -> Response:
    settings = _settings()
    form = await _parse_form_body(request)
    _validate_csrf_token(request, form)
    clinic_name = form.get("clinic_name", "")
    clinic_slug = form.get("clinic_slug", "")
    clinic_phone = form.get("clinic_phone", "")
    clinic_timezone = form.get("clinic_timezone", "Asia/Almaty")
    email = form.get("email", "")
    password = form.get("password", "")
    password_confirm = form.get("password_confirm", "")

    error: str | None = None

    async with SessionLocal() as session:
        if normalize_owner_email(email) is None:
            error = "Укажите корректный email."
        elif validate_password(password) is None:
            error = "Пароль должен содержать минимум 8 символов."
        elif password != password_confirm:
            error = "Пароли не совпадают."
        else:
            try:
                clinic, owner = await create_clinic_with_owner(
                    session,
                    clinic_name=clinic_name,
                    clinic_slug=clinic_slug,
                    clinic_phone=clinic_phone,
                    clinic_timezone=clinic_timezone,
                    owner_email=email,
                    owner_password=password,
                )
            except ValueError as exc:
                error = str(exc)
            else:
                await session.commit()
                response = _redirect("/owner/dashboard")
                _set_owner_cookie(response, owner, settings)
                return response

    csrf_token = _get_or_create_csrf_token(request)
    body = auth_card(
        title="Регистрация клиники",
        subtitle="Создайте клинику и сразу подключите первого владельца.",
        form_action="/owner/register",
        submit_label="Создать клинику",
        email_value=email,
        error=error,
        include_confirm_password=True,
        extra_fields_html=_registration_fields(
            clinic_name=clinic_name,
            clinic_slug=clinic_slug,
            clinic_phone=clinic_phone,
            clinic_timezone=clinic_timezone,
        ),
        footer_html='<p class="form-footer">Если владелец уже создан, перейдите ко <a href="/owner/login">входу</a>.</p>',
        csrf_token=csrf_token,
    )
    return _html_response(
        request,
        content=layout(
            title="Регистрация клиники",
            heading="Регистрация клиники",
            body_html=body,
            csrf_token=csrf_token,
            page_key="auth",
        ),
        status_code=status.HTTP_400_BAD_REQUEST,
    )


@router.get("/owner/login", response_class=HTMLResponse)
async def owner_login_page(request: Request) -> Response:
    context = await _get_owner_context(request)
    if context is not None:
        return _redirect("/owner/dashboard")

    csrf_token = _get_or_create_csrf_token(request)
    body = auth_card(
        title="Вход для владельца",
        subtitle="Используйте аккаунт клиники, чтобы открыть панель заявок.",
        form_action="/owner/login",
        submit_label="Войти",
        footer_html='<p class="form-footer">Если владелец еще не создан, откройте <a href="/owner/register">регистрацию</a>.</p>',
        csrf_token=csrf_token,
    )
    return _html_response(
        request,
        content=layout(
            title="Вход владельца",
            heading="Вход владельца",
            body_html=body,
            csrf_token=csrf_token,
            page_key="auth",
        ),
    )


@router.post("/owner/login")
async def owner_login_submit(request: Request) -> Response:
    settings = _settings()
    form = await _parse_form_body(request)
    _validate_csrf_token(request, form)
    email = form.get("email", "")
    password = form.get("password", "")

    async with SessionLocal() as session:
        owner = await authenticate_owner(session, email=email, password=password)

    if owner is None:
        csrf_token = _get_or_create_csrf_token(request)
        body = auth_card(
            title="Вход для владельца",
            subtitle="Используйте аккаунт клиники, чтобы открыть панель заявок.",
            form_action="/owner/login",
            submit_label="Войти",
            email_value=email,
            error="Неверный email или пароль.",
            footer_html='<p class="form-footer">Если владелец еще не создан, откройте <a href="/owner/register">регистрацию</a>.</p>',
            csrf_token=csrf_token,
        )
        return _html_response(
            request,
            content=layout(
                title="Вход владельца",
                heading="Вход владельца",
                body_html=body,
                csrf_token=csrf_token,
                page_key="auth",
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    response = _redirect("/owner/dashboard")
    _set_owner_cookie(response, owner, settings)
    return response


@router.post("/owner/logout")
async def owner_logout(request: Request) -> Response:
    form = await _parse_form_body(request)
    _validate_csrf_token(request, form)
    response = _redirect("/owner/login")
    response.delete_cookie(_settings().auth_cookie_name, path="/")
    response.delete_cookie(_settings().auth_csrf_cookie_name, path="/")
    return response


@router.get("/owner/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request) -> Response:
    context = await _require_owner_context(request)
    if isinstance(context, RedirectResponse):
        return context

    csrf_token = _get_or_create_csrf_token(request)
    status_filter = normalize_whitespace(request.query_params.get("status"))
    search_query = normalize_whitespace(request.query_params.get("q"))

    async with SessionLocal() as session:
        result = await list_bookings(
            session,
            clinic_id=context.clinic.id,
            clinic_timezone=context.clinic.timezone,
            status_filter=status_filter,
            search_query=search_query,
        )
        telegram_config = await get_clinic_telegram_config(session, context.clinic.id)

    rows_html = "".join(
        (
            "<tr>"
            f'<td><a href="/owner/bookings/{item.booking_id}">{escape(item.patient_name)}</a></td>'
            f"<td>{escape(item.patient_phone)}</td>"
            f"<td>{escape(item.service_type)}</td>"
            f"<td>{escape(item.preferred_datetime)}</td>"
            f'<td><span class="status-badge status-{escape(item.status)}">{escape(status_label(item.status))}</span></td>'
            f"<td>{escape(item.created_at)}</td>"
            "</tr>"
        )
        for item in result.items
    )
    if not rows_html:
        rows_html = '<tr><td colspan="6" class="empty-state">Пока нет заявок для отображения.</td></tr>'

    counts = result.counts
    telegram_status = describe_telegram_connection(telegram_config)
    dashboard_body = (
        '<section class="stats-grid">'
        '<article class="stat-card">'
        '<span class="stat-label">Ожидают</span>'
        f'<strong>{counts.get("pending", 0)}</strong>'
        '<p class="stat-help">Новые заявки, которые ждут подтверждения.</p>'
        "</article>"
        '<article class="stat-card">'
        '<span class="stat-label">Подтверждены</span>'
        f'<strong>{counts.get("confirmed", 0)}</strong>'
        '<p class="stat-help">Записи, которые уже подтверждены владельцем.</p>'
        "</article>"
        '<article class="stat-card">'
        '<span class="stat-label">Отменены</span>'
        f'<strong>{counts.get("cancelled", 0)}</strong>'
        '<p class="stat-help">Заявки, снятые с обработки или отклоненные.</p>'
        "</article>"
        '<article class="stat-card stat-card-wide">'
        '<div class="card-heading">'
        '<span class="stat-label">Telegram</span>'
        '<a class="text-link" href="/owner/settings">Открыть настройки</a>'
        "</div>"
        f"<strong>{escape(telegram_status.label)}</strong>"
        f'<p class="status-note">{escape(telegram_status.detail)}</p>'
        "</article>"
        "</section>"
        '<section class="panel panel-section">'
        '<div class="section-head">'
        '<div>'
        "<h2>Заявки</h2>"
        '<p class="panel-subtitle">Следите за новыми обращениями, фильтруйте список и открывайте карточку заявки для обработки.</p>'
        "</div>"
        "</div>"
        '<form method="get" class="filters">'
        '<label class="field compact-field">'
        "<span>Поиск</span>"
        f'<input type="search" name="q" value="{escape(search_query)}" placeholder="Имя, телефон, услуга">'
        "</label>"
        '<label class="field compact-field">'
        "<span>Статус</span>"
        f'<select name="status">{_status_options(status_filter)}</select>'
        "</label>"
        '<button class="primary-button" type="submit">Применить</button>'
        '<a class="ghost-link" href="/owner/dashboard">Сбросить</a>'
        "</form>"
        '<div class="table-wrap">'
        '<table class="bookings-table">'
        "<thead><tr><th>Пациент</th><th>Телефон</th><th>Услуга</th><th>Когда удобно</th><th>Статус</th><th>Создана</th></tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table>"
        "</div>"
        "</section>"
    )

    return _html_response(
        request,
        content=layout(
            title="Панель владельца",
            heading="Заявки клиники",
            body_html=dashboard_body,
            owner_email=context.owner.email,
            clinic_name=context.clinic.name,
            csrf_token=csrf_token,
            page_key="dashboard",
        ),
    )


@router.get("/owner/settings", response_class=HTMLResponse)
async def owner_settings_page(request: Request) -> Response:
    context = await _require_owner_context(request)
    if isinstance(context, RedirectResponse):
        return context

    csrf_token = _get_or_create_csrf_token(request)
    saved = request.query_params.get("saved") == "1"
    async with SessionLocal() as session:
        config = await get_clinic_telegram_config(session, context.clinic.id)

    body = _settings_body(
        clinic=context.clinic,
        config=config,
        settings=_settings(),
        saved=saved,
        csrf_token=csrf_token,
    )
    return _html_response(
        request,
        content=layout(
            title="Настройки клиники",
            heading="Настройки клиники",
            body_html=body,
            owner_email=context.owner.email,
            clinic_name=context.clinic.name,
            csrf_token=csrf_token,
            page_key="settings",
        ),
    )


@router.post("/owner/settings/telegram")
async def owner_settings_telegram_submit(request: Request) -> Response:
    context = await _require_owner_context(request)
    if isinstance(context, RedirectResponse):
        return context

    settings = _settings()
    form = await _parse_form_body(request)
    _validate_csrf_token(request, form)
    bot_token = form.get("bot_token", "")
    error: str | None = None

    async with SessionLocal() as session:
        clinic = await session.get(Clinic, context.clinic.id)
        if clinic is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clinic not found.")

        try:
            await configure_clinic_telegram_bot(
                session,
                clinic=clinic,
                bot_token=bot_token,
                settings=settings,
                crypto_service=request.app.state.crypto_service,
                bot_registry=request.app.state.bot_registry,
                dispatcher=request.app.state.dispatcher,
            )
        except (RuntimeError, ValueError) as exc:
            error = str(exc)
        else:
            await session.commit()
            return _redirect("/owner/settings?saved=1")

        config = await get_clinic_telegram_config(session, context.clinic.id)

    csrf_token = _get_or_create_csrf_token(request)
    body = _settings_body(
        clinic=context.clinic,
        config=config,
        settings=settings,
        error=error,
        csrf_token=csrf_token,
    )
    return _html_response(
        request,
        content=layout(
            title="Настройки клиники",
            heading="Настройки клиники",
            body_html=body,
            owner_email=context.owner.email,
            clinic_name=context.clinic.name,
            csrf_token=csrf_token,
            page_key="settings",
        ),
        status_code=status.HTTP_400_BAD_REQUEST,
    )


@router.get("/owner/bookings/{booking_id}", response_class=HTMLResponse)
async def owner_booking_detail(
    booking_id: uuid.UUID,
    request: Request,
) -> Response:
    context = await _require_owner_context(request)
    if isinstance(context, RedirectResponse):
        return context

    csrf_token = _get_or_create_csrf_token(request)
    async with SessionLocal() as session:
        detail = await get_booking_detail(
            session,
            clinic_id=context.clinic.id,
            clinic_timezone=context.clinic.timezone,
            booking_id=booking_id,
        )

    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")

    message_html = "".join(
        (
            '<article class="message-card">'
            f'<div class="message-meta"><strong>{escape(message.role)}</strong><span>{escape(message.created_at)}</span></div>'
            f'<p>{escape(message.content)}</p>'
            "</article>"
        )
        for message in detail.messages
    )
    if not message_html:
        message_html = '<div class="empty-message-state">Для этой заявки пока нет истории сообщений.</div>'

    detail_body = (
        '<section class="detail-grid">'
        '<div class="panel panel-section">'
        '<div class="section-head">'
        '<div>'
        f"<h2>{escape(detail.patient_name)}</h2>"
        '<p class="panel-subtitle">Карточка заявки с контактами, временем записи и текущим статусом.</p>'
        "</div>"
        f'<span class="status-badge status-{escape(detail.status)}">{escape(status_label(detail.status))}</span>'
        "</div>"
        '<dl class="detail-list">'
        f"<div><dt>Телефон</dt><dd>{escape(detail.patient_phone)}</dd></div>"
        f"<div><dt>Услуга</dt><dd>{escape(detail.service_type)}</dd></div>"
        f"<div><dt>Нормализованное время</dt><dd>{escape(detail.preferred_datetime)}</dd></div>"
        f"<div><dt>Исходный ввод</dt><dd>{escape(detail.preferred_datetime_raw)}</dd></div>"
        f"<div><dt>Создана</dt><dd>{escape(detail.created_at)}</dd></div>"
        f"<div><dt>Обновлена</dt><dd>{escape(detail.updated_at)}</dd></div>"
        "</dl>"
        '<div class="action-group">'
        '<p class="action-label">Изменить статус</p>'
        f'<form action="/owner/bookings/{detail.booking_id}/status" method="post" class="status-form">'
        f"{csrf_input(csrf_token)}"
        '<input type="hidden" name="status" value="confirmed">'
        '<button class="primary-button" type="submit">Подтвердить</button>'
        "</form>"
        f'<form action="/owner/bookings/{detail.booking_id}/status" method="post" class="status-form">'
        f"{csrf_input(csrf_token)}"
        '<input type="hidden" name="status" value="cancelled">'
        '<button class="secondary-button" type="submit">Отменить</button>'
        "</form>"
        f'<form action="/owner/bookings/{detail.booking_id}/status" method="post" class="status-form">'
        f"{csrf_input(csrf_token)}"
        '<input type="hidden" name="status" value="pending">'
        '<button class="ghost-button" type="submit">Вернуть в ожидание</button>'
        "</form>"
        "</div>"
        "</div>"
        '<div class="panel panel-section">'
        '<div class="section-head">'
        '<div>'
        "<h2>История диалога</h2>"
        '<p class="panel-subtitle">Сообщения пациента и ответы бота по этой записи.</p>'
        "</div>"
        '<a class="ghost-link" href="/owner/dashboard">Назад к списку</a>'
        "</div>"
        f"{message_html}"
        "</div>"
        "</section>"
    )

    return _html_response(
        request,
        content=layout(
            title="Детали заявки",
            heading="Карточка заявки",
            body_html=detail_body,
            owner_email=context.owner.email,
            clinic_name=context.clinic.name,
            csrf_token=csrf_token,
            page_key="booking_detail",
        ),
    )


@router.post("/owner/bookings/{booking_id}/status")
async def owner_booking_status_update(
    booking_id: uuid.UUID,
    request: Request,
) -> Response:
    context = await _require_owner_context(request)
    if isinstance(context, RedirectResponse):
        return context

    form = await _parse_form_body(request)
    _validate_csrf_token(request, form)
    status_value = normalize_whitespace(form.get("status"))
    if not status_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Status is required.")

    async with SessionLocal() as session:
        updated = await update_booking_status(
            session,
            clinic_id=context.clinic.id,
            booking_id=booking_id,
            new_status=status_value,
        )
        if updated is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status transition.")
        await session.commit()

    return _redirect(f"/owner/bookings/{booking_id}")


async def _get_owner_context(request: Request) -> OwnerContext | None:
    settings = _settings()
    token = request.cookies.get(settings.auth_cookie_name)
    session_data = verify_session_token(token, settings.auth_secret_key)
    if session_data is None:
        return None

    async with SessionLocal() as session:
        owner = await get_clinic_user_by_id(session, session_data.clinic_user_id)
        if owner is None or not owner.is_active:
            return None

        clinic = await session.get(Clinic, owner.clinic_id)
        if clinic is None:
            return None

        return OwnerContext(clinic=clinic, owner=owner)


async def _require_owner_context(request: Request) -> OwnerContext | RedirectResponse:
    context = await _get_owner_context(request)
    if context is None:
        return _redirect("/owner/login")
    return context


async def _parse_form_body(request: Request) -> dict[str, str]:
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items() if values}


def _validate_csrf_token(request: Request, form: dict[str, str]) -> None:
    settings = _settings()
    form_token = normalize_whitespace(form.get("csrf_token"))
    cookie_token = request.cookies.get(settings.auth_csrf_cookie_name)

    if not form_token or not cookie_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed.")

    if not hmac.compare_digest(form_token, cookie_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed.")

    if verify_csrf_token(form_token, settings.auth_secret_key) is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed.")


def _get_or_create_csrf_token(request: Request) -> str:
    settings = _settings()
    token = request.cookies.get(settings.auth_csrf_cookie_name)
    if verify_csrf_token(token, settings.auth_secret_key) is not None:
        return token

    return create_csrf_token(
        secret_key=settings.auth_secret_key,
        max_age_seconds=settings.auth_csrf_max_age_seconds,
    )


def _html_response(
    request: Request,
    *,
    content: str,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    response = HTMLResponse(content=content, status_code=status_code)
    response.headers["Cache-Control"] = "no-store"
    _set_csrf_cookie(response, _get_or_create_csrf_token(request), _settings())
    return response


def _set_owner_cookie(response: RedirectResponse, owner: ClinicUser, settings: Settings) -> None:
    token = create_session_token(
        clinic_user_id=owner.id,
        secret_key=settings.auth_secret_key,
        max_age_seconds=settings.auth_session_max_age_seconds,
    )
    response.set_cookie(
        settings.auth_cookie_name,
        token,
        httponly=True,
        max_age=settings.auth_session_max_age_seconds,
        expires=settings.auth_session_max_age_seconds,
        samesite="lax",
        secure=settings.app_env != "development",
        path="/",
    )


def _set_csrf_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        settings.auth_csrf_cookie_name,
        token,
        httponly=True,
        max_age=settings.auth_csrf_max_age_seconds,
        expires=settings.auth_csrf_max_age_seconds,
        samesite="strict",
        secure=settings.app_env != "development",
        path="/",
    )


def _status_options(selected: str) -> str:
    options = [
        ("", "Все"),
        ("pending", "Ожидают"),
        ("confirmed", "Подтверждены"),
        ("cancelled", "Отменены"),
    ]
    html = []
    for value, label in options:
        selected_attr = ' selected="selected"' if value == selected else ""
        html.append(f'<option value="{escape(value)}"{selected_attr}>{escape(label)}</option>')
    return "".join(html)


def _registration_fields(
    *,
    clinic_name: str = "",
    clinic_slug: str = "",
    clinic_phone: str = "",
    clinic_timezone: str = "Asia/Almaty",
) -> str:
    return (
        '<label class="field">'
        "<span>Название клиники</span>"
        f'<input type="text" name="clinic_name" value="{escape(clinic_name)}" required>'
        "</label>"
        '<label class="field">'
        "<span>Slug клиники</span>"
        f'<input type="text" name="clinic_slug" value="{escape(clinic_slug)}" placeholder="dental-almaty">'
        "</label>"
        '<label class="field">'
        "<span>Телефон клиники</span>"
        f'<input type="tel" name="clinic_phone" value="{escape(clinic_phone)}" placeholder="+77001234567">'
        "</label>"
        '<label class="field">'
        "<span>Timezone</span>"
        f'<input type="text" name="clinic_timezone" value="{escape(clinic_timezone)}" required>'
        "</label>"
    )


def _settings_body(
    *,
    clinic: Clinic,
    config: ClinicTelegramConfig | None,
    settings: Settings,
    saved: bool = False,
    error: str | None = None,
    csrf_token: str,
) -> str:
    notices = ""
    if saved:
        notices += '<div class="notice success">Настройки Telegram сохранены.</div>'
    if error:
        notices += f'<div class="notice error">{escape(error)}</div>'

    status = describe_telegram_connection(config)
    webhook_url = settings.build_telegram_webhook_url(clinic.slug)
    username_html = ""
    if config is not None and config.bot_username:
        username_html = f"<div><dt>Bot username</dt><dd>@{escape(config.bot_username)}</dd></div>"

    webhook_html = (
        '<div><dt>Webhook URL</dt><dd>TELEGRAM_WEBHOOK_BASE_URL не настроен.</dd></div>'
        if webhook_url is None
        else f"<div><dt>Webhook URL</dt><dd>{escape(webhook_url)}</dd></div>"
    )

    registered_html = ""
    if config is not None and config.last_webhook_registered_at is not None:
        registered_html = (
            "<div><dt>Webhook обновлен</dt>"
            f"<dd>{escape(config.last_webhook_registered_at.strftime('%d.%m.%Y %H:%M'))}</dd></div>"
        )

    return (
        f"{notices}"
        '<section class="detail-grid settings-grid">'
        '<div class="panel panel-section">'
        '<div class="section-head">'
        '<div>'
        "<h2>Профиль клиники</h2>"
        '<p class="panel-subtitle">Базовая информация о клинике и текущий статус канала связи.</p>'
        "</div>"
        f'<span class="status-badge status-{escape(status.tone)}">{escape(status.label)}</span>'
        "</div>"
        '<dl class="detail-list">'
        f"<div><dt>Название</dt><dd>{escape(clinic.name)}</dd></div>"
        f"<div><dt>Slug</dt><dd>{escape(clinic.slug)}</dd></div>"
        f"<div><dt>Телефон</dt><dd>{escape(clinic.phone_number or 'Не указан')}</dd></div>"
        f"<div><dt>Timezone</dt><dd>{escape(clinic.timezone)}</dd></div>"
        f"{username_html}"
        f"{webhook_html}"
        f"{registered_html}"
        f"<div><dt>Статус</dt><dd>{escape(status.detail)}</dd></div>"
        "</dl>"
        "</div>"
        '<div class="panel panel-section">'
        '<div class="section-head">'
        '<div>'
        "<h2>Подключение Telegram</h2>"
        '<p class="panel-subtitle">Сохраните токен бота клиники. После проверки мы зарегистрируем webhook для этого slug.</p>'
        "</div>"
        "</div>"
        '<form action="/owner/settings/telegram" method="post" class="stack-form">'
        f"{csrf_input(csrf_token)}"
        '<label class="field">'
        "<span>Токен бота</span>"
        '<input type="password" name="bot_token" autocomplete="off" placeholder="123456:ABCDEF..." required>'
        "</label>"
        '<button class="primary-button" type="submit">Сохранить токен</button>'
        "</form>"
        "</div>"
        "</section>"
    )


def _redirect(url: str) -> RedirectResponse:
    response = RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)
    response.headers["Cache-Control"] = "no-store"
    return response


def _settings() -> Settings:
    return get_settings()

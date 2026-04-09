from __future__ import annotations

import uuid
from dataclasses import dataclass
from html import escape
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.models import Clinic, ClinicUser
from app.owner.render import auth_card, layout, status_label
from app.services.auth_service import (
    authenticate_owner,
    clinic_has_owner,
    create_owner_user,
    create_session_token,
    get_clinic_user_by_id,
    normalize_owner_email,
    validate_password,
    verify_session_token,
)
from app.services.clinic_service import get_clinic_by_slug
from app.services.dashboard_service import get_booking_detail, list_bookings, update_booking_status
from app.services.normalization import normalize_whitespace


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
    settings = _settings()
    context = await _get_owner_context(request)

    async with SessionLocal() as session:
        clinic = await _load_owner_clinic(session, settings)
        if await clinic_has_owner(session, clinic.id):
            return _redirect("/owner/dashboard" if context is not None else "/owner/login")

    body = auth_card(
        title="Создание владельца клиники",
        subtitle="Первый владелец получает доступ к панели заявок.",
        form_action="/owner/register",
        submit_label="Создать аккаунт",
        include_confirm_password=True,
        footer_html='<p class="form-footer">Если аккаунт уже создан, перейдите ко <a href="/owner/login">входу</a>.</p>',
    )
    return HTMLResponse(content=layout(title="Регистрация владельца", heading="Регистрация владельца", body_html=body))


@router.post("/owner/register")
async def owner_register_submit(request: Request) -> Response:
    settings = _settings()
    form = await _parse_form_body(request)
    email = form.get("email", "")
    password = form.get("password", "")
    password_confirm = form.get("password_confirm", "")

    error: str | None = None

    async with SessionLocal() as session:
        clinic = await _load_owner_clinic(session, settings)
        if await clinic_has_owner(session, clinic.id):
            return _redirect("/owner/login")

        if normalize_owner_email(email) is None:
            error = "Укажите корректный email."
        elif validate_password(password) is None:
            error = "Пароль должен содержать минимум 8 символов."
        elif password != password_confirm:
            error = "Пароли не совпадают."
        else:
            try:
                owner = await create_owner_user(
                    session,
                    clinic=clinic,
                    email=email,
                    password=password,
                )
            except ValueError as exc:
                error = str(exc)
            else:
                await session.commit()
                response = _redirect("/owner/dashboard")
                _set_owner_cookie(response, owner, settings)
                return response

    body = auth_card(
        title="Создание владельца клиники",
        subtitle="Первый владелец получает доступ к панели заявок.",
        form_action="/owner/register",
        submit_label="Создать аккаунт",
        email_value=email,
        error=error,
        include_confirm_password=True,
        footer_html='<p class="form-footer">Если аккаунт уже создан, перейдите ко <a href="/owner/login">входу</a>.</p>',
    )
    return HTMLResponse(content=layout(title="Регистрация владельца", heading="Регистрация владельца", body_html=body), status_code=status.HTTP_400_BAD_REQUEST)


@router.get("/owner/login", response_class=HTMLResponse)
async def owner_login_page(request: Request) -> Response:
    context = await _get_owner_context(request)
    if context is not None:
        return _redirect("/owner/dashboard")

    body = auth_card(
        title="Вход для владельца",
        subtitle="Используйте аккаунт клиники, чтобы открыть панель заявок.",
        form_action="/owner/login",
        submit_label="Войти",
        footer_html='<p class="form-footer">Если владелец еще не создан, откройте <a href="/owner/register">регистрацию</a>.</p>',
    )
    return HTMLResponse(content=layout(title="Вход владельца", heading="Вход владельца", body_html=body))


@router.post("/owner/login")
async def owner_login_submit(request: Request) -> Response:
    settings = _settings()
    form = await _parse_form_body(request)
    email = form.get("email", "")
    password = form.get("password", "")

    async with SessionLocal() as session:
        owner = await authenticate_owner(session, email=email, password=password)

    if owner is None:
        body = auth_card(
            title="Вход для владельца",
            subtitle="Используйте аккаунт клиники, чтобы открыть панель заявок.",
            form_action="/owner/login",
            submit_label="Войти",
            email_value=email,
            error="Неверный email или пароль.",
            footer_html='<p class="form-footer">Если владелец еще не создан, откройте <a href="/owner/register">регистрацию</a>.</p>',
        )
        return HTMLResponse(
            content=layout(title="Вход владельца", heading="Вход владельца", body_html=body),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    response = _redirect("/owner/dashboard")
    _set_owner_cookie(response, owner, settings)
    return response


@router.post("/owner/logout")
async def owner_logout() -> Response:
    response = _redirect("/owner/login")
    response.delete_cookie(_settings().auth_cookie_name, path="/")
    return response


@router.get("/owner/dashboard", response_class=HTMLResponse)
async def owner_dashboard(request: Request) -> Response:
    context = await _require_owner_context(request)
    if isinstance(context, RedirectResponse):
        return context

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
    dashboard_body = (
        '<section class="stats-grid">'
        f'<div class="stat-card"><span>Ожидают</span><strong>{counts.get("pending", 0)}</strong></div>'
        f'<div class="stat-card"><span>Подтверждены</span><strong>{counts.get("confirmed", 0)}</strong></div>'
        f'<div class="stat-card"><span>Отменены</span><strong>{counts.get("cancelled", 0)}</strong></div>'
        "</section>"
        '<section class="panel">'
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

    return HTMLResponse(
        content=layout(
            title="Панель владельца",
            heading="Заявки клиники",
            body_html=dashboard_body,
            owner_email=context.owner.email,
            clinic_name=context.clinic.name,
        )
    )


@router.get("/owner/bookings/{booking_id}", response_class=HTMLResponse)
async def owner_booking_detail(
    booking_id: uuid.UUID,
    request: Request,
) -> Response:
    context = await _require_owner_context(request)
    if isinstance(context, RedirectResponse):
        return context

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
        '<div class="panel">'
        '<div class="panel-head">'
        '<div>'
        '<p class="eyebrow">Booking</p>'
        f"<h2>{escape(detail.patient_name)}</h2>"
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
        f'<form action="/owner/bookings/{detail.booking_id}/status" method="post" class="status-form">'
        '<input type="hidden" name="status" value="confirmed">'
        '<button class="primary-button" type="submit">Подтвердить</button>'
        "</form>"
        f'<form action="/owner/bookings/{detail.booking_id}/status" method="post" class="status-form">'
        '<input type="hidden" name="status" value="cancelled">'
        '<button class="secondary-button" type="submit">Отменить</button>'
        "</form>"
        f'<form action="/owner/bookings/{detail.booking_id}/status" method="post" class="status-form">'
        '<input type="hidden" name="status" value="pending">'
        '<button class="ghost-button" type="submit">Вернуть в ожидание</button>'
        "</form>"
        "</div>"
        '<div class="panel">'
        '<div class="panel-head">'
        "<h2>История диалога</h2>"
        '<a class="ghost-link" href="/owner/dashboard">Назад к списку</a>'
        "</div>"
        f"{message_html}"
        "</div>"
        "</section>"
    )

    return HTMLResponse(
        content=layout(
            title="Детали заявки",
            heading="Карточка заявки",
            body_html=detail_body,
            owner_email=context.owner.email,
            clinic_name=context.clinic.name,
        )
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


async def _load_owner_clinic(session: AsyncSession, settings: Settings) -> Clinic:
    clinic = await get_clinic_by_slug(session, settings.test_clinic_slug)
    if clinic is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Clinic is not configured yet.",
        )
    return clinic


async def _parse_form_body(request: Request) -> dict[str, str]:
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {
        key: values[0]
        for key, values in parsed.items()
        if values
    }


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
        samesite="lax",
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


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


def _settings() -> Settings:
    return get_settings()

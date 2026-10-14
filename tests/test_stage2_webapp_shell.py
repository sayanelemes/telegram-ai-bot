import pytest
from httpx import AsyncClient, ASGITransport
from app.keyboards.inline import get_webapp_inline_keyboard
from app.handlers.short_links import cmd_stats, cmd_tasks
from unittest.mock import AsyncMock


def test_webapp_deep_link_generation():
    # Test default
    kb1 = get_webapp_inline_keyboard()
    assert kb1 is not None
    btn1 = kb1.inline_keyboard[0][0]
    assert btn1.web_app is not None
    assert btn1.text == "🍎 Открыть приложение"

    # Test deep link with screen and params
    kb2 = get_webapp_inline_keyboard(
        text="🍳 Рецепт",
        screen="recipe",
        params={"remaining": 850}
    )
    btn2 = kb2.inline_keyboard[0][0]
    assert "screen=recipe" in btn2.web_app.url
    assert "remaining=850" in btn2.web_app.url


@pytest.mark.asyncio
async def test_static_webapp_serving(app_instance):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Request index.html
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "Bulking Super-App" in resp.text
        assert "tab-today" in resp.text
        assert "tab-food" in resp.text
        assert "tab-workout" in resp.text
        assert "tab-money" in resp.text
        assert "tab-more" in resp.text

        # Request style.css
        css_resp = await client.get("/style.css")
        assert css_resp.status_code == 200

        # Request app.js
        js_resp = await client.get("/app.js")
        assert js_resp.status_code == 200
        assert "Bulking Super-App" in js_resp.text


@pytest.mark.asyncio
async def test_short_link_commands():
    msg = AsyncMock()
    msg.answer = AsyncMock()

    await cmd_stats(msg)
    assert msg.answer.called
    assert "статистика" in msg.answer.call_args[0][0].lower()

    await cmd_tasks(msg)
    assert "задачи" in msg.answer.call_args[0][0].lower()

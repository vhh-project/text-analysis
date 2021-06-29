from django.contrib.staticfiles import finders
import pytest


@pytest.mark.django_db
def test_default_page(admin_client):
    response = admin_client.get("/main/")
    assert response.status_code == 200


def test_spritemap_exists():
    assert finders.find('img/extern/spritemap.png') is not None
    assert finders.find('img/extern/spritemap@2x.png') is not None

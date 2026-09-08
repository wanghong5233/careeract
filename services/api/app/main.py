from services.api.app.factory import create_app
from services.api.app.settings import get_settings

app = create_app(get_settings())

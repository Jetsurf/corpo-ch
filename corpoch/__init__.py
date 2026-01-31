from .celery import app as celery

__all__ = ['celery']
__version__ = '0.1.0'
__title__ = 'Corpo CH'
__url__ = 'https://github.com/Jetsurf/corpo'
__user_agent__ = f'{__title__} - v{__version__} - <{__url__}>'
NAME = f'{__title__} v{__version__}'

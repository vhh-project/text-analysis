from django import template
from django.templatetags.static import static as _system_static
from django_global_request.middleware import get_request

register = template.Library()


@register.simple_tag
def save_static(*args, **kwargs):
    request = get_request()
    return request.META.get("SCRIPT_NAME", "") + _system_static(*args, **kwargs)


@register.filter
def previous(some_list, current_index):
    try:
        return some_list[int(current_index) - 1]
    except:
        return ''

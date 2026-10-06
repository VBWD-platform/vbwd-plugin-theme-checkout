"""``ConfirmationSectionRegistry`` — the twin of fe-user ``registries/checkoutConfirmationRegistry.ts``.

Keeps ``/checkout/confirmation`` agnostic of what was bought: a selling adapter
(theme_booking's BookingConfirmationDetails, …) registers a
:class:`ConfirmationSection` from ``on_enable`` and the CheckoutConfirmation
widget renders every section that applies to the viewer's invoice, each in a
``.card`` after the invoice details (``CheckoutConfirmationView.vue``'s
``<component v-for="plugin in confirmationPlugins" class="card">``). Sections
read the owner's invoice, so they only exist in the region re-render (bearer).
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional

from plugins.theme.theme.theme_request import ThemeRequest

from .checkout_sources import running_theme_checkout_plugin

# (invoice, theme_request) -> the section template's ``section.context``; ``None``
# renders nothing (the Vue component's root ``v-if`` when its data is unavailable).
SectionContextBuilder = Callable[
    [Mapping[str, Any], ThemeRequest], Optional[Mapping[str, Any]]
]


@dataclass(frozen=True)
class ConfirmationSection:
    """One plugin's block on the confirmation page; lower ``order`` comes first."""

    name: str
    owner_fe_user_plugin: str
    applies: Callable[[Mapping[str, Any]], bool]
    template: str
    build_context: SectionContextBuilder
    order: int = 0


class ConfirmationSectionRegistry:
    """Name → section; a re-registration replaces the name and moves it last (the SPA)."""

    def __init__(self, is_fe_user_plugin_enabled: Callable[[str], bool]) -> None:
        self._is_fe_user_plugin_enabled = is_fe_user_plugin_enabled
        self._sections_by_name: Dict[str, ConfirmationSection] = {}

    def register(self, section: ConfirmationSection) -> None:
        self._sections_by_name.pop(section.name, None)
        self._sections_by_name[section.name] = section

    def sections_for(self, invoice: Mapping[str, Any]) -> List[ConfirmationSection]:
        """Enabled sections that apply, by ``order`` then registration order."""
        applying = (
            section
            for section in self._sections_by_name.values()
            if self._is_fe_user_plugin_enabled(section.owner_fe_user_plugin)
            and section.applies(invoice)
        )
        return sorted(applying, key=lambda section: section.order)


def resolve_confirmation_section_registry() -> ConfirmationSectionRegistry:
    """The running app's registry; selling adapters register their sections here."""
    registry: ConfirmationSectionRegistry = (
        running_theme_checkout_plugin().confirmation_section_registry
    )
    return registry

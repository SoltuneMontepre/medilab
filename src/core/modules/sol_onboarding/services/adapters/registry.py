from .base import Adapter

ADAPTERS: dict[str, type[Adapter]] = {}


# Class decorator registering an adapter under the key sources name it by.
def register[AdapterT: type[Adapter]](key: str):
    def decorator(adapter_class: AdapterT) -> AdapterT:
        ADAPTERS[key] = adapter_class
        return adapter_class

    return decorator


def adapter_for(source) -> Adapter:
    try:
        return ADAPTERS[source.adapter](source)
    except KeyError:
        raise ValueError(f"No adapter is registered as {source.adapter!r}.") from None

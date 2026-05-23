_source_registry: dict[str, type] = {}
_extension_registry: dict[str, type] = {}

def register_source(name: str):
	def decorator(cls):
		_source_registry[name] = cls
		return cls
	return decorator

def register_extension(name: str):
	def decorator(cls):
		_extension_registry[name] = cls
		return cls
	return decorator

def get_source_class(name: str):
	return _source_registry[name]

def get_extension_class(name: str):
	return _extension_registry[name]

def create_source(name: str, **kwargs):
    cls = get_source_class(name)
    return cls(**kwargs)

def create_extension(name: str, **kwargs):
    cls = get_extension_class(name)
    return cls(**kwargs)
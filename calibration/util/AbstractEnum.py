from enum import Enum
from typing import Type, Optional, List, Dict, Any

from django.core.cache import cache
from django.db import models


class AbstractEnum(Enum):
    """
    This abstract class provides an enum-like interface that is dynamically synced with the database.

    - The class allows you to define specific enum members for values that are explicitly referenced
      in the code, ensuring they are easy to access and reducing the risk of typos or case mismatches.

    - In addition to the explicitly defined enum members, the class dynamically loads values
      from the corresponding database table and stores them in cache.
      This ensures that all current database values are available, even if they aren't explicitly defined
      in the enum. The cached values prevent repeated database queries, improving performance.

    - Subclasses of AbstractEnum must override the `get_model()` method to specify the associated model,
      and can optionally override the `get_filter()` method to apply custom filters (e.g., `is_active=True`).

    This setup allows the enum to function both as a traditional enum for specific values and as a dynamic
    provider of all relevant database entries.
    """

    @classmethod
    def get_model(cls) -> Type[models.Model]:
        """
        This method should be overridden in subclasses to return the model class
        associated with the enum. For example, StatusEnum would return the Status model.
        """
        raise NotImplementedError("Subclasses must define a 'get_model' method")

    @classmethod
    def get_names(cls) -> List[str]:
        """
        Returns a list of names from the cached enum values.
        This method retrieves the names of the items stored in the cache.
        """
        # Ensure cache is loaded if not already cached
        items = cache.get(f'{cls.__name__}_cache')
        if items is None:
            cls.load_items()
            items = cache.get(f'{cls.__name__}_cache')

        # Return a list of names
        return [item.name for item in items.values()]

    @classmethod
    def get_filter(cls) -> Optional[Dict[str, Any]]:
        """
        This method can be overridden in subclasses to provide custom filters when querying the database.
        By default, it returns None, meaning no filters are applied.
        If the subclass has an `is_active` field, for example, it can override this method to return
        {'is_active': True}.
        """
        return None

    @classmethod
    def load_items(cls) -> None:
        """
        This method loads items from the database using the optional filters provided by the `get_filter()` method.
        If no filter is defined, all items are loaded. The items are then stored in the cache to avoid
        repeated database queries.
        """
        # Get the model defined in the subclass (e.g., Status)
        model = cls.get_model()

        # Get the custom filter (if any) from the subclass
        filter_criteria = cls.get_filter() or {}

        # Query items from the database, applying the filter criteria
        items = model.objects.filter(**filter_criteria)

        # Store the results in a dictionary with the item's name as the key
        item_dict = {item.name: item for item in items}

        # Store the dictionary in the cache with a 1-hour timeout
        cache.set(f'{cls.__name__}_cache', item_dict, timeout=3600)

    @classmethod
    def get_instance(cls, name: str) -> models.Model:
        """
        This method retrieves the model instance corresponding to the given value
        (e.g., 'Running') from the cache. If the cache is empty, it reloads the active
        items from the database. If the value doesn't exist in the cache, a ValueError is raised.

        :param name: The name of the item to retrieve (e.g., 'Running')
        :return: The model instance corresponding to the value
        :raises: ValueError if the value does not exist in the cache
        """
        # Attempt to retrieve cached items
        items = cache.get(f'{cls.__name__}_cache')
        if items is None:
            # If cache is empty, reload active items from the database
            cls.load_items()
            items = cache.get(f'{cls.__name__}_cache')

        # Get the instance corresponding to the provided value
        instance = items.get(name)
        if instance is None:
            # Raise an error if the value isn't found in the cache
            raise ValueError(f"No matching database entry for value '{name}' in {cls.__name__}.")
        return instance

    @classmethod
    def from_enum(cls, enum_member: Enum) -> models.Model:
        """
        This method allows you to retrieve the model instance associated with a specific
        enum member (e.g., StatusEnum.RUNNING). It internally calls get_instance() with
        the enum member's value.

        :param enum_member: The enum member (e.g., StatusEnum.RUNNING)
        :return: The model instance corresponding to the enum member
        """
        # Get the instance by the enum member's value
        return cls.get_instance(enum_member.value)

    @classmethod
    def active_choices_with_fields(cls, fields: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        This method returns a list of items from the database, with the specified
        fields included in each item. By default, it includes 'name' and 'description'.
        Intended for use by the front-end.

        :param fields: A list of fields to include for each item (e.g., ['name', 'description'])
        :return: A list of dictionaries, where each dictionary contains the requested fields
                 for an item (e.g., [{'name': 'Running', 'description': '...'}])
        """
        if fields is None:
            # Default to including the 'name' and 'description' fields
            fields = ['name', 'description']

        # Attempt to retrieve cached items
        items = cache.get(f'{cls.__name__}_cache')
        if items is None:
            # If cache is empty, reload active items from the database
            cls.load_items()
            items = cache.get(f'{cls.__name__}_cache')

        # Return a list of dictionaries containing the specified fields
        return [
            {field: getattr(item, field) for field in fields}
            for item in items.values()
        ]

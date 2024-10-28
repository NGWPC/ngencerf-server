from enum import Enum
from typing import Optional, List, Dict, Any, Generic
from typing import Type, TypeVar

from django.core.cache import cache
from django.db import models

# Create a generic type variable for models
T = TypeVar('T', bound=models.Model)


class AbstractEnum(Generic[T], Enum):
    """
    This abstract class provides an enum-like interface that is dynamically synced with the database.

    - This class allows specific enum members to be defined for values referenced directly in the code,
      reducing the risk of typos or mismatches. These specific members must be present in the database.

    - In addition to explicitly defined members, this class dynamically loads additional values
      from the database and caches them. This ensures that all relevant database values are accessible
      without repeated queries.

    - Subclasses must override the `get_model()` method to specify the associated model and may optionally
      override `get_filter()` to apply a custom filter, such as `is_active=True`.
    """

    @classmethod
    def get_model(cls) -> Type[T]:
        """
        To be implemented by each subclass to return the model associated with the enum.

        For example, a StatusEnum subclass would return the Status model.
        """
        raise NotImplementedError("Subclasses must define a 'get_model' method")

    @classmethod
    def get_aliases(cls) -> Dict[str, List[str]]:
        """
        Optionally overridden by subclasses to provide aliases for enum members.

        :return: A dictionary of aliases for enum members, defaulting to an empty dictionary.
        """
        return {}

    @classmethod
    def get_names(cls) -> List[str]:
        """
        Retrieves the names of the cached enum items. If the cache is empty, items are reloaded from the database.

        :return: A list of names for the enum items
        """
        # Attempt to get items from the cache, and reload if cache is empty
        items = cache.get(f'{cls.__name__}_cache')
        if items is None:
            cls.load_items()
            items = cache.get(f'{cls.__name__}_cache')

        # Return just the names of the items
        return [item.name for item in items.values()]

    @classmethod
    def get_all_valid_names(cls) -> List[str]:
        """
        Retrieves a list of all valid names for the enum, including any aliases defined by the subclass.

        This supports flexibility by allowing multiple names (aliases) for the same enum member.

        :return: A list of valid names, including aliases
        """
        # Retrieve the valid names from the enum itself
        valid_names = set(cls.get_names())
        aliases = cls.get_aliases()  # Call the optional get_aliases() method

        for main_value, alias_list in aliases.items():
            main_value_value = main_value.value

            if main_value_value in valid_names:
                valid_names.update(alias_list)

        return list(valid_names)

    @classmethod
    def get_filter(cls) -> Optional[Dict[str, Any]]:
        """
        Optional: Subclasses can override this to specify custom filters (e.g., `{'is_active': True}`)
        to apply when loading items from the database.

        By default, no filters are applied.

        :return: A dictionary of filters or None if no filters are needed
        """
        return None

    @classmethod
    def load_items(cls) -> None:
        """
        Loads items from the database, applying filters specified in `get_filter()`. Results are cached
        to avoid redundant queries, where each item is stored by name.

        This method is called automatically if the cache is empty.
        """
        # Get the model defined in the subclass (e.g., Status)
        model = cls.get_model()

        # Get any filter criteria specified in the subclass
        filter_criteria = cls.get_filter() or {}

        # Query the model using the filter criteria and build a dictionary of items keyed by name
        items = model.objects.filter(**filter_criteria)
        item_dict = {item.name: item for item in items}

        # Store the item dictionary in cache
        cache.set(f'{cls.__name__}_cache', item_dict, timeout=None)

    @classmethod
    def get_instance(cls, name: str) -> T:
        """
        Retrieves the model instance corresponding to the given name or alias from the cache,
        reloading from the database if necessary. Raises a ValueError if the name is not found.

        :param name: The name or alias of the item to retrieve (e.g., 'Running' or 'User Upload')
        :return: The model instance associated with the name
        :raises: ValueError if no matching name or alias exists in the cache
        """
        # Convert name to lowercase for case-insensitive matching
        name = name.lower()

        # Attempt to retrieve cached items, reloading if necessary
        items = cache.get(f'{cls.__name__}_cache')
        if items is None:
            # If cache is empty, reload active items from the database
            cls.load_items()
            items = cache.get(f'{cls.__name__}_cache')

        # Create a lookup dictionary with lowercase names for case-insensitive retrieval
        items_lower = {item_name.lower(): item for item_name, item in items.items()}

        # Include aliases in the lookup dictionary
        aliases = cls.get_aliases()
        for main_value, alias_list in aliases.items():
            main_item = items_lower.get(main_value.value.lower())  # Find the main item
            if main_item:
                for alias in alias_list:
                    items_lower[alias.lower()] = main_item  # Map each alias to the main item

        # Retrieve the instance by lowercase name or raise an error if not found
        instance = items_lower.get(name)
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
        :return: The model instance associated with the enum member
        """
        # Uses get_instance to retrieve based on the enum member's value
        return cls.get_instance(enum_member.value)

    @classmethod
    def active_choices_with_fields(cls, fields: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Returns a list of items from the database, including only the specified fields in each item
        (defaults to 'name' and 'description'). This method is useful for front-end selections.

        :param fields: A list of fields to include for each item (e.g., ['name', 'description'])
        :return: A list of dictionaries, where each dictionary contains the requested fields
                 for an item (e.g., [{'name': 'Running', 'description': '...'}])
        """
        if fields is None:
            # Default to including the 'name' and 'description' fields
            fields = ['name', 'description']

        # Retrieve cached items, reloading if the cache is empty
        items = cache.get(f'{cls.__name__}_cache')
        if items is None:
            # If cache is empty, reload active items from the database
            cls.load_items()
            items = cache.get(f'{cls.__name__}_cache')

        # Return each item as a dictionary of the specified fields
        return [
            {field: getattr(item, field) for field in fields}
            for item in items.values()
        ]

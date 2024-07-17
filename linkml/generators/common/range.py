"""
Abstract generator classes for slot ranges
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Union, ClassVar, Optional, Type
from dataclasses import dataclass

from linkml_runtime import SchemaView
from linkml_runtime.linkml_model import Element
from linkml_runtime.linkml_model.meta import SlotDefinition, ArrayExpression, AnonymousSlotExpression

from linkml.generators.common.build import RangeResult

_BOUNDED_ARRAY_FIELDS = ("exact_number_dimensions", "minimum_number_dimensions", "maximum_number_dimensions")


@dataclass
class RangeGenerator(ABC):

    @classmethod
    def build(cls, slot: Union[SlotDefinition, AnonymousSlotExpression], sv: SchemaView, **kwargs) -> RangeResult:
        slot = cls.custom_handler(slot, sv, **kwargs)
        if isinstance(slot, RangeResult):
            return slot

        # Special ranges that are processed independently
        if slot.any_of and all([s.range for s in slot.any_of]):
            return cls.any_of(slot, sv, **kwargs)
        if slot.array:
            return cls.array(slot, sv, **kwargs)

        # Ranges that can be modified by later modifier methods
        if slot.designates_type:
            result = cls.designates_type(slot, sv)
        elif slot.ifabsent is not None:
            result = cls.ifabsent(slot, sv)
        elif slot.range in sv.all_classes():
            result = cls.class_slot(slot, sv)
        elif slot.range in sv.all_enums():
            result = cls.enum_slot(slot, sv)
        elif slot.range in sv.all_types():
            result = cls.type_slot(slot, sv)
        elif slot.range is None:
            result = cls.default_range(slot, sv)
        else:
            raise ValueError(f"Slot range not recognized by any handler. Got slot:\n{slot}")

        # Modifiers to generated ranges
        if slot.multivalued:
            result = cls.multivalued(result, sv)
        elif slot.inlined:
            result = cls.inlined(result, sv)

        return result

    @classmethod
    def custom_handler(cls, slot: SlotDefinition, sv: SchemaView, **kwargs) -> Union[RangeResult, SlotDefinition]:
        """
        override default mapping from slot definition to handler method.

        Return a :class:`.RangeResult` from this if it is intended to call a specific handler,
        return the :class:`.SlotDefinition` if it is intended to modify the slot before range generation.

        """
        return slot

    @classmethod
    def default_range(cls, slot: SlotDefinition, sv: SchemaView) -> RangeResult:
        return cls.type_slot(sv.schema.default_range, sv)

    @classmethod
    @abstractmethod
    def type_slot(cls, slot: Union[SlotDefinition, str], sv: SchemaView) -> RangeResult:
        """
        Most basic kind of slot range -- generators must be able to handle linkml types

        This handler method must also support the name of the type passed in as
        a string, in addition to retrieving it from the range.
        """

    @classmethod
    def array(
        cls, slot: SlotDefinition, sv: SchemaView, representation: str, dtype: Union[str, Element]
    ) -> RangeResult:
        raise NotImplementedError("array ranges not supported by this generator")

    @classmethod
    def any_of(cls, slot: SlotDefinition, sv: SchemaView, **kwargs) -> RangeResult:
        raise NotImplementedError("any_of not supported by this generator")

    @classmethod
    def designates_type(cls, slot: SlotDefinition, sv: SchemaView) -> RangeResult:
        raise NotImplementedError("designates type not supported by this generator")

    @classmethod
    def ifabsent(cls, slot: SlotDefinition, sv: SchemaView) -> RangeResult:
        raise NotImplementedError("ifabsent not supported by this generator")

    @classmethod
    def class_slot(cls, slot: SlotDefinition, sv: SchemaView) -> RangeResult:
        raise NotImplementedError("class slot not implemented by this generator")

    @classmethod
    def enum_slot(cls, slot: SlotDefinition, sv: SchemaView) -> RangeResult:
        raise NotImplementedError("enum slot not implemented by this generator")

    @classmethod
    def multivalued(cls, slot: RangeResult, sv: SchemaView) -> RangeResult:
        raise NotImplementedError("multivalued generation not supported by this generator")

    @classmethod
    def inlined(cls, slot: RangeResult, sv: SchemaView) -> RangeResult:
        if slot.inlined_as_list:
            return cls.inlined_as_list(slot, sv)
        else:
            return cls.inlined_as_dict(slot, sv)

    @classmethod
    def inlined_as_list(cls, slot: RangeResult, sv: SchemaView) -> RangeResult:
        raise NotImplementedError("inlined_as_list not supported by this generator")

    @classmethod
    def inlined_as_dict(cls, slot: RangeResult, sv: SchemaView) -> RangeResult:
        raise NotImplementedError("inlined_as_dict not supported by this generator")

    @classmethod
    def class_range_has_identifier(cls, slot: SlotDefinition, sv: SchemaView) -> bool:
        """
        Check if the range class of a slot has an identifier slot, via both slot.any_of and slot.range
        Should return False if the range is not a class, and also if the range is a class but has no
        identifier slot
        """
        has_identifier_slot = False
        if slot.any_of:
            for slot_range in slot.any_of:
                any_of_range = slot_range.range
                if any_of_range in sv.all_classes() and sv.get_identifier_slot(any_of_range, use_key=True) is not None:
                    has_identifier_slot = True
        if slot.range in sv.all_classes() and sv.get_identifier_slot(slot.range, use_key=True) is not None:
            has_identifier_slot = True
        return has_identifier_slot


class ArrayRangeGenerator(ABC):
    """
    Metaclass for generating a given format of array range.

    See :ref:`array-forms` for more details on array range forms.

    These classes do only enough validation of the array specification to decide
    which kind of representation to generate. Proper value validation should
    happen elsewhere (ie. in the metamodel and generated :class:`.ArrayExpression` class.)

    Each of the array representation generation methods should be able to handle
    the supported pydantic versions (currently still 1 and 2).

    Notes:

        When checking for array specification, recall that there is a semantic difference between
        ``None`` and ``False`` , particularly for :attr:`.ArrayExpression.max_number_dimensions` -
        check for absence of specification with ``is None`` rather than checking for truthiness/falsiness
        (unless that's what you intend to do ofc ;)

    Attributes:
        array (:class:`.ArrayExpression` ): Array to create a range for
        dtype (Union[str, :class:`.Element` ): dtype of the entire array as a string

    """
    representations: ClassVar[Enum]
    """
    The enum of arrays that the ArrayRangeGenerator supports for this particular Generator.
    
    Each Subclass will define ``repr`` as one of the values from this enum
    """

    REPR: ClassVar[Enum]

    def __init__(self, array: Optional[ArrayExpression], dtype: Union[str, Element]):
        self.array = array
        self.dtype = dtype

    def make(self) -> RangeResult:
        """Create the string form of the array representation"""
        if not self.array.dimensions and not self.has_bounded_dimensions:
            # any-shaped array
            return self.any_shape(self.array)
        elif not self.array.dimensions and self.has_bounded_dimensions:
            return self.bounded_dimensions(self.array)
        elif self.array.dimensions and not self.has_bounded_dimensions:
            return self.parameterized_dimensions(self.array)
        else:
            return self.complex_dimensions(self.array)

    @property
    def has_bounded_dimensions(self) -> bool:
        """Whether the :class:`.ArrayExpression` has some shape specification aside from ``dimensions``"""
        return any([getattr(self.array, arr_field, None) is not None for arr_field in _BOUNDED_ARRAY_FIELDS])

    @classmethod
    def get_generator(cls, repr: Union[Enum, str]) -> Type["ArrayRangeGenerator"]:
        """Get the generator class for a given array representation"""
        for subclass in cls.__subclasses__():
            if repr in (subclass.REPR, subclass.REPR.value):
                return subclass
        raise ValueError(f"Generator for array representation {repr} not found!")

    @abstractmethod
    def any_shape(self, array: Optional[ArrayExpression] = None) -> RangeResult:
        """Any shaped array!"""
        pass

    @abstractmethod
    def bounded_dimensions(self, array: ArrayExpression) -> RangeResult:
        """Array shape specified numerically, without axis parameterization"""
        pass

    @abstractmethod
    def parameterized_dimensions(self, array: ArrayExpression) -> RangeResult:
        """Array shape specified with ``dimensions`` without additional parameterized dimensions"""
        pass

    @abstractmethod
    def complex_dimensions(self, array: ArrayExpression) -> RangeResult:
        """Array shape with both ``parameterized`` and ``bounded`` dimensions"""
        pass

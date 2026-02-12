"""
Regression test for inventory/utils_verticals.py syntax and import integrity.

This test ensures that:
1. The module compiles without SyntaxError
2. The module can be imported successfully
3. Key functions are available and callable
4. Sidebar items include Data Correction where applicable

Created to prevent regression from SyntaxError incidents (e.g., unclosed brackets
in sidebar item lists during Data Correction feature implementation).
"""
import pytest
from django.test import TestCase


class UtilsVerticalsSyntaxTest(TestCase):
    """Test that utils_verticals.py is syntactically correct and imports successfully."""

    def test_module_imports_successfully(self):
        """Test that inventory.utils_verticals can be imported without errors."""
        try:
            from inventory import utils_verticals
        except SyntaxError as e:
            self.fail(f"SyntaxError when importing utils_verticals: {e}")
        except Exception as e:
            self.fail(f"Unexpected error when importing utils_verticals: {e}")

    def test_key_functions_exist(self):
        """Test that key functions are defined and accessible."""
        from inventory import utils_verticals
        
        required_functions = [
            'get_vertical_kind',
            'get_vertical_dashboard_url',
            'get_onboarding_steps',
            'get_vertical_display_name',
            'get_vertical_sidebar_items',
        ]
        
        for func_name in required_functions:
            self.assertTrue(
                hasattr(utils_verticals, func_name),
                f"Function {func_name} not found in utils_verticals"
            )
            func = getattr(utils_verticals, func_name)
            self.assertTrue(
                callable(func),
                f"{func_name} is not callable"
            )

    def test_sidebar_items_returns_list_for_phones(self):
        """Test that get_vertical_sidebar_items returns a valid list for 'phones'."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        items = get_vertical_sidebar_items('phones')
        
        self.assertIsInstance(items, list, "Sidebar items should be a list")
        self.assertGreater(len(items), 0, "Sidebar should have at least one item")
        
        # Each item should be a dict with required keys
        for item in items:
            self.assertIsInstance(item, dict, "Each sidebar item should be a dict")
            self.assertIn('key', item, "Each item should have a 'key'")
            self.assertIn('label', item, "Each item should have a 'label'")

    def test_sidebar_items_returns_list_for_gym(self):
        """Test that get_vertical_sidebar_items returns a valid list for 'gym'."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        items = get_vertical_sidebar_items('gym')
        
        self.assertIsInstance(items, list, "Sidebar items should be a list")
        self.assertGreater(len(items), 0, "Sidebar should have at least one item")

    def test_sidebar_items_returns_list_for_clothing(self):
        """Test that get_vertical_sidebar_items returns a valid list for 'clothing'."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        items = get_vertical_sidebar_items('clothing')
        
        self.assertIsInstance(items, list, "Sidebar items should be a list")
        self.assertGreater(len(items), 0, "Sidebar should have at least one item")

    def test_data_correction_item_present_for_registered_verticals(self):
        """Test that Data Correction menu item is present for verticals registered in corrections framework."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        # These verticals are registered in corrections.registry
        registered_verticals = ['phones', 'gym', 'clothing']
        
        for vertical in registered_verticals:
            items = get_vertical_sidebar_items(vertical)
            correction_items = [i for i in items if i.get('key') == 'data_correction']
            
            self.assertEqual(
                len(correction_items), 1,
                f"Expected exactly 1 Data Correction item for {vertical}, found {len(correction_items)}"
            )
            
            # Verify the structure of the Data Correction item
            correction_item = correction_items[0]
            self.assertEqual(correction_item.get('label'), 'Data Correction')
            self.assertEqual(correction_item.get('icon'), 'bi-pencil-square')
            self.assertTrue(correction_item.get('require_manager'), 
                          "Data Correction should require manager role")

    def test_no_duplicate_sidebar_items(self):
        """Test that there are no duplicate sidebar items based on 'key'."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        verticals = ['phones', 'gym', 'clothing', 'farm', 'welding', 'hardware', 'car_hire']
        
        for vertical in verticals:
            items = get_vertical_sidebar_items(vertical)
            keys = [item.get('key') for item in items if item.get('key')]
            
            # Check for duplicates
            seen = set()
            duplicates = []
            for key in keys:
                if key in seen:
                    duplicates.append(key)
                seen.add(key)
            
            self.assertEqual(
                len(duplicates), 0,
                f"Found duplicate keys in {vertical} sidebar: {duplicates}"
            )

    def test_sidebar_items_structure_integrity(self):
        """Test that all sidebar items have proper structure (no malformed dicts)."""
        from inventory.utils_verticals import get_vertical_sidebar_items
        
        verticals = ['phones', 'gym', 'clothing']
        required_keys = ['key', 'label', 'section']
        
        for vertical in verticals:
            items = get_vertical_sidebar_items(vertical)
            
            for idx, item in enumerate(items):
                # Check it's a dict
                self.assertIsInstance(
                    item, dict,
                    f"{vertical} sidebar item #{idx} is not a dict: {type(item)}"
                )
                
                # Check required keys
                for required_key in required_keys:
                    self.assertIn(
                        required_key, item,
                        f"{vertical} sidebar item #{idx} missing '{required_key}': {item}"
                    )
















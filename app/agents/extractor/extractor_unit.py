# test_extractor.py

import tkinter as tk
from tkinter import filedialog
import json

# Import the function from our extractor script
from extractor import get_contents

class ExtractorTester:
    def __init__(self):
        # We initialize the tkinter root here and immediately hide it
        # so we only see the file dialog, not an empty gray window.
        self.root = tk.Tk()
        self.root.withdraw()

    def select_file(self):
        """Opens a file explorer window to select a document."""
        file_path = filedialog.askopenfilename(
            title="Select a contract document to test",
            filetypes=[
                ("Supported Documents", "*.pdf *.docx *.xlsx *.xls"),
                ("PDF Files", "*.pdf"),
                ("Word Documents", "*.docx"),
                ("Excel Files", "*.xlsx *.xls"),
                ("All Files", "*.*")
            ]
        )
        return file_path

    def _print_formatted(self, title, data):
        """Helper method to neatly print Pydantic models."""
        print(f"\n{'='*50}")
        print(f" {title.upper()} ".center(50, '='))
        print(f"{'='*50}")

        if not data:
            print("No data found or returned as None.")
            return

        # If it's a list (like models, normal_models, commitments)
        if isinstance(data, list):
            if len(data) == 0:
                print("[] (Empty List)")
            for i, item in enumerate(data):
                print(f"\n--- Record {i + 1} ---")
                # Handle Pydantic V1 (.dict()) and V2 (.model_dump())
                item_dict = item.model_dump() if hasattr(item, 'model_dump') else item.dict()
                print(json.dumps(item_dict, indent=4))
        
        # If it's a single object (like header)
        else:
            item_dict = data.model_dump() if hasattr(data, 'model_dump') else data.dict()
            print(json.dumps(item_dict, indent=4))

    def run(self):
        print("Waiting for file selection...")
        file_path = self.select_file()

        if not file_path:
            print("No file was selected. Test aborted.")
            return

        print(f"\nFile selected: {file_path}")
        print("Firing up the AI model to extract data. This may take a moment...")

        try:
            # Call the target function
            header, models, normal_models, commitments = get_contents(file_path)

            # Print results out neatly
            self._print_formatted("Header Staging", header)
            self._print_formatted("Models Staging", models)
            self._print_formatted("Normal Models Staging", normal_models)
            self._print_formatted("Commitments Staging", commitments)

            print("\n" + "="*50)
            print("✅ Extraction test completed successfully!")

        except Exception as e:
            print(f"\n❌ An error occurred during extraction:\n{e}")

if __name__ == "__main__":
    tester = ExtractorTester()
    tester.run()
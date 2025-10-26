import os
import tkinter as tk
from tkinter import filedialog
from PIL import Image


# Function to create thumbnails
def create_thumbnails():
    input_directory = input_dir_entry.get()
    output_directory = output_dir_entry.get()

    # Ensure the output directory exists
    os.makedirs(output_directory, exist_ok=True)

    for filename in os.listdir(input_directory):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
            try:
                with Image.open(os.path.join(input_directory, filename)) as img:
                    img.thumbnail((50, 50))
                    img.save(os.path.join(output_directory, filename))
                    status_label.config(text=f"Thumbnail created for: {filename}")
            except Exception as e:
                status_label.config(text=f"Error processing {filename}: {str(e)}")


# Create the main GUI window
root = tk.Tk()
root.title("Thumbnail Creator")

# Input directory selection
input_dir_label = tk.Label(root, text="Select Input Directory:")
input_dir_label.pack()
input_dir_entry = tk.Entry(root, width=50)
input_dir_entry.pack()
input_dir_button = tk.Button(root, text="Browse", command=lambda: input_dir_entry.insert(0, filedialog.askdirectory()))
input_dir_button.pack()

# Output directory selection
output_dir_label = tk.Label(root, text="Select Output Directory:")
output_dir_label.pack()
output_dir_entry = tk.Entry(root, width=50)
output_dir_entry.pack()
output_dir_button = tk.Button(root, text="Browse",
                              command=lambda: output_dir_entry.insert(0, filedialog.askdirectory()))
output_dir_button.pack()

# Create thumbnails button
create_button = tk.Button(root, text="Create Thumbnails", command=create_thumbnails)
create_button.pack()

# Status label to display messages
status_label = tk.Label(root, text="")
status_label.pack()

root.mainloop()


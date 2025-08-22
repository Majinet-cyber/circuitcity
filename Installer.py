import tkinter as tk
from tkinter import messagebox
import subprocess


def install_package():
    package_name = package_entry.get().strip()
    if not package_name:
        messagebox.showerror("Error", "Please enter a package name.")
        return

    try:
        subprocess.run(["pip", "install", package_name], check=True)
        messagebox.showinfo("Success", f"'{package_name}' installed successfully.")
    except subprocess.CalledProcessError:
        messagebox.showerror("Error", f"Failed to install '{package_name}'.")


root = tk.Tk()
root.title("PIP Package Installer")
root.geometry("400x200")

tk.Label(root, text="Enter Package Name:").pack(pady=5)
package_entry = tk.Entry(root, width=40)
package_entry.pack(pady=5)

tk.Button(root, text="Install", command=install_package).pack(pady=10)

root.mainloop()

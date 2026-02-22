import json
import os
import copy
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import subprocess
import tempfile

CONFIG_FILE = "config.json"
class PlaneConfigEditor:

    def __init__(self, root):
        self.root = root
        self.root.title("PlayerPlaneConfig Editor")
        self.file_path = None
        self.original_data = None
        self.data = None
        self.parameters = {}
        self.param_widgets = {}
        self.dragging_point = None
        self.create_ui()
        self.line_map = {}   # maps matplotlib line → (type, index, axis)
        self.engine_version = "VER_UE4_18"
        self.mappings_name = None
        self.temp_json_path = None
        self.uasset_path = None
        self.uassetgui_path = None
        self.load_config()
        self.fixed_enums = {
            "DriftPostStallManeuverability": {
                "Kulbit": "EDriftPostStallManeuverability::Kulbit",
                "Cobra": "EDriftPostStallManeuverability::Cobra",
                "None": "EDriftPostStallManeuverability::None"
            }
        }

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                self.uassetgui_path = config.get("uassetgui_path")
        else:
            self.uassetgui_path = None
        if self.uassetgui_path:
            self.uassetgui_label.config(
                text=f"UAssetGUI: {os.path.dirname(self.uassetgui_path)}",
                fg="green"
            )

    def save_config(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump({
                "uassetgui_path": self.uassetgui_path
            }, f, indent=2)

    def select_uassetgui(self):
        path = filedialog.askopenfilename(
            title="Select UAssetGUI.exe",
            filetypes=[("Executable", "*.exe")]
        )
        if path:
            self.uassetgui_path = path
            self.save_config()
            messagebox.showinfo("Saved", "UAssetGUI path saved.")
        self.uassetgui_label.config(
            text=f"UAssetGUI: {os.path.dirname(self.uassetgui_path)}",
            fg="green"
        )

    # =====================================================
    # UI
    # =====================================================

    def create_ui(self):
        # ---------------- Top Bar ----------------
        top = tk.Frame(self.root)
        top.pack(fill="x")
        tk.Button(top, text="Open JSON/UASSET", command=self.load_file).pack(side="left")
        tk.Label(top, text="New PlaneID").pack(side="left")
        self.new_id = tk.Entry(top, width=8)
        self.new_id.pack(side="left")
        tk.Button(top, text="Replace", command=self.replace_plane_id).pack(side="left")
        tk.Button(top, text="Save", command=self.save_file).pack(side="right")
        tk.Button(top, text="Revert", command=self.revert_changes).pack(side="right")
        tk.Button(top, text="Set UAssetGUI.exe", command=self.select_uassetgui).pack(side="left")
        self.uassetgui_label = tk.Label(top, text="UAssetGUI: Not Set", fg="gray")
        self.uassetgui_label.pack(side="left", padx=10)
        # ---------------- Main Split Layout ----------------
        main_container = tk.PanedWindow(
            self.root,
            orient=tk.HORIZONTAL,
            sashrelief=tk.RAISED,
            sashwidth=6
        )
        main_container.pack(fill="both", expand=True)
        left_frame = tk.Frame(main_container)
        right_frame = tk.Frame(main_container)
        main_container.add(left_frame, minsize=300)
        main_container.add(right_frame, minsize=400)
        # ---------------- Scrollable Inspector ----------------
        canvas = tk.Canvas(left_frame)
        scrollbar = tk.Scrollbar(left_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        # ---------------- Graphs ----------------
        self.fig, (self.ax1, self.ax2, self.ax3) = plt.subplots(3, 1, figsize=(6, 8))
        self.fig.tight_layout(pad=3)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        # Enable dragging
        self.canvas.mpl_connect("pick_event", self.on_pick)
        self.canvas.mpl_connect("motion_notify_event", self.on_drag)
        self.canvas.mpl_connect("button_release_event", self.on_release)

    # =====================================================
    # File Handling
    # =====================================================

    def load_file(self):
        path = filedialog.askopenfilename(
            filetypes=[
                ("Plane Files", "*.json *.uasset"),
                ("JSON", "*.json"),
                ("UAsset", "*.uasset")
            ]
        )
        if not path:
            return
        # ------------------------------------------
        # If JSON → load normally
        # ------------------------------------------
        if path.endswith(".json"):
            self.file_path = path
            with open(path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        # ------------------------------------------
        # If UASSET → convert to JSON first
        # ------------------------------------------
        elif path.endswith(".uasset"):
            if not self.uassetgui_path:
                messagebox.showerror("Error", "Please set UAssetGUI.exe first.")
                return
            self.uasset_path = path
            temp_json = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
            temp_json.close()
            cmd = [
                self.uassetgui_path,
                "tojson",
                path,
                temp_json.name,
                "VER_UE4_18"
            ]
            try:
                subprocess.run(cmd, check=True)
            except Exception as e:
                messagebox.showerror("Conversion Error", str(e))
                return
            self.file_path = temp_json.name
            with open(temp_json.name, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        # ------------------------------------------
        self.original_data = copy.deepcopy(self.data)
        self.parameters = self.extract_all_parameters()
        self.build_parameter_inspector()
        self.extract_graph_data()
        self.update_graphs()

    def save_file(self):
        if not self.file_path:
            return
        self.apply_changes_to_json()
        # Always save JSON first
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        # If editing a .uasset, convert back
        if self.uasset_path:
            cmd = [
                self.uassetgui_path,
                "fromjson",
                self.file_path,
                self.uasset_path
            ]
            try:
                subprocess.run(cmd, check=True)
                messagebox.showinfo("Saved", "UAsset saved successfully.")
            except Exception as e:
                messagebox.showerror("Conversion Error", str(e))
        else:
            messagebox.showinfo("Saved", "JSON saved successfully.")

    def revert_changes(self):
        if self.original_data:
            self.data = copy.deepcopy(self.original_data)
            self.parameters = self.extract_all_parameters()
            self.build_parameter_inspector()
            self.extract_graph_data()
            self.update_graphs()

    # =====================================================
    # Parameter Extraction
    # =====================================================

    def extract_all_parameters(self):
        parameters = {}
        self.enum_types = {}   # store enum type info
        values = self.data["Exports"][0]["Table"]["Data"][0]["Value"]
        for entry in values:
            name = entry["Name"]
            value = entry["Value"]
            entry_type = entry.get("$type", "")
            # ---------------- ENUM ----------------
            if "EnumPropertyData" in entry_type:
                parameters[name] = value  # current enum value (string)
                self.enum_types[name] = entry["EnumType"]
            # ---------------- BOOL ----------------
            elif isinstance(value, bool):
                parameters[name] = value
            # ---------------- NUMBER / STRING ----------------
            elif isinstance(value, (int, float, str)):
                try:
                    parameters[name] = round(float(value), 3)
                except:
                    parameters[name] = value
            # ---------------- VECTOR ----------------
            elif isinstance(value, list):
                vec = value[0]["Value"]
                parameters[name] = {
                    "X": round(float(vec["X"]), 3),
                    "Y": round(float(vec["Y"]), 3),
                    "Z": round(float(vec["Z"]), 3)
                }
        return parameters

    def get_enum_options(self, enum_type_name):
        options = []
        name_map = self.data.get("NameMap", [])
        for name in name_map:
            if name.startswith(enum_type_name + "::"):
                options.append(name)
        return options

    # =====================================================
    # Inspector with Collapsible Categories
    # =====================================================

    def build_parameter_inspector(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.param_widgets = {}
        categories = {
            "Speed": [],
            "Rotation": [],
            "Drift": [],
            "Other": []
        }
        for name in self.parameters:
            if "Speed" in name:
                categories["Speed"].append(name)
            elif "Rot" in name:
                categories["Rotation"].append(name)
            elif "Drift" in name:
                categories["Drift"].append(name)
            else:
                categories["Other"].append(name)
        for cat, names in categories.items():
            self.create_category(cat, names)

    def create_category(self, title, names):
        outer = tk.Frame(self.scrollable_frame, bd=1, relief="solid")
        outer.pack(fill="x", pady=6, padx=6)
        header = tk.Label(
            outer,
            text=title,
            bg="#2b2b2b",
            fg="white",
            anchor="w",
            padx=6,
            pady=4
        )
        header.pack(fill="x")
        content = tk.Frame(outer)
        content.pack(fill="x", padx=8, pady=6)
        content.grid_columnconfigure(1, weight=1)
        def toggle(event=None):
            if content.winfo_ismapped():
                content.pack_forget()
            else:
                content.pack(fill="x", padx=8, pady=6)
        header.bind("<Button-1>", toggle)
        for row, name in enumerate(names):
            value = self.parameters[name]
            lbl = tk.Label(content, text=name, anchor="w")
            lbl.grid(row=row, column=0, sticky="ew", padx=5, pady=3)
            value_frame = tk.Frame(content)
            value_frame.grid(row=row, column=1, sticky="ew")
            if isinstance(value, dict):
                entries = {}
                for axis in ["X", "Y", "Z"]:
                    e = tk.Entry(value_frame, width=7, justify="center")
                    e.insert(0, value[axis])
                    e.pack(side="left", fill="x", expand=True,)
                    e.bind("<KeyRelease>", self.live_update)
                    entries[axis] = e
                self.param_widgets[name] = entries
            else:
                # -------- ENUM --------
                if hasattr(self, "fixed_enums") and name in self.fixed_enums:
                    enum_map = self.fixed_enums[name]
                    combo = ttk.Combobox(
                        value_frame,
                        values=list(enum_map.keys()),
                        state="readonly"
                    )
                    # Convert stored value → clean label
                    reverse_map = {v: k for k, v in enum_map.items()}
                    if value in reverse_map:
                        combo.set(reverse_map[value])
                    else:
                        combo.set(list(enum_map.keys())[0])
                    combo.pack(side="left", fill="x", expand=True)
                    combo.bind("<<ComboboxSelected>>", self.live_update)
                    self.param_widgets[name] = combo
                # -------- NORMAL VALUE --------
                else:
                    e = tk.Entry(value_frame, width=12, justify="center")
                    e.insert(0, value)
                    e.pack(side="left", fill="x", expand=True)
                    e.bind("<KeyRelease>", self.live_update)
                    self.param_widgets[name] = e

    # =====================================================
    # Live Update
    # =====================================================

    def ensure_name_in_namemap(self, name_string):
        if "NameMap" not in self.data:
            return
        if name_string not in self.data["NameMap"]:
            self.data["NameMap"].append(name_string)

    def live_update(self, event=None):
        try:
            self.apply_changes_to_json()
        except:
            pass

    def apply_changes_to_json(self):
        values = self.data["Exports"][0]["Table"]["Data"][0]["Value"]
        for entry in values:
            name = entry["Name"]
            if name not in self.param_widgets:
                continue
            widget = self.param_widgets[name]
            # -------- VECTOR --------
            if isinstance(widget, dict):
                vec = entry["Value"][0]["Value"]
                for axis in ["X", "Y", "Z"]:
                    try:
                        vec[axis] = float(widget[axis].get())
                    except:
                        pass
            # -------- NORMAL --------
            else:
                # -------- ENUM --------
                if hasattr(self, "fixed_enums") and name in self.fixed_enums:
                    enum_map = self.fixed_enums[name]
                    selected_label = widget.get()
                    enum_value = enum_map[selected_label]
                    # Ensure enum string exists in NameMap
                    self.ensure_name_in_namemap(enum_value)
                    entry["Value"] = enum_value
                # -------- NORMAL --------
                else:
                    try:
                        entry["Value"] = float(widget.get())
                    except:
                        entry["Value"] = widget.get()
        self.parameters = self.extract_all_parameters()
        self.extract_graph_data()
        self.update_graphs()

    # =====================================================
    # Graph Handling
    # =====================================================

    def extract_graph_data(self):
        self.speed_graph = []
        self.diff_nose = []
        self.speed_rot = []
        self.rot_grav = []
        indexed_speed = {}
        indexed_diff = {}
        for name, value in self.parameters.items():
            if name.startswith("SpeedGraph"):
                idx = int(name.replace("SpeedGraph", ""))
                indexed_speed[idx] = float(value)
            elif name.startswith("DiffNoseVelocityR"):
                idx = int(name.replace("DiffNoseVelocityR", ""))
                indexed_diff[idx] = float(value)
            elif name.startswith("SpeedRot"):
                self.speed_rot.append([value["X"], value["Y"], value["Z"]])
            elif name.startswith("RotGravR"):
                self.rot_grav.append([value["X"], value["Y"], value["Z"]])
        # Rebuild in correct index order
        for i in sorted(indexed_speed.keys()):
            self.speed_graph.append(indexed_speed[i])
            self.diff_nose.append(indexed_diff.get(i, 0.0))

    def update_graphs(self):
        self.ax1.clear()
        self.ax2.clear()
        self.ax3.clear()
        self.line_map.clear()
        if not self.speed_graph:
            return
        # ================= GRAPH 1 =================
        line1, = self.ax1.plot(
            self.speed_graph,
            self.diff_nose,
            marker="o",
            picker=5,
        )
        self.ax1.set_title("DiffNoseVelocityR")
        self.line_map[line1] = ("diff_nose", None, None)
        # ================= GRAPH 2 =================
        if self.speed_rot:
            x_vals = self.speed_graph
            rx = [v[0] for v in self.speed_rot]
            ry = [v[1] for v in self.speed_rot]
            rz = [v[2] for v in self.speed_rot]
            line_rx, = self.ax2.plot(x_vals, rx, marker="o", picker=5, label="Pitch")
            line_ry, = self.ax2.plot(x_vals, ry, marker="o", picker=5, label="Yaw")
            line_rz, = self.ax2.plot(x_vals, rz, marker="o", picker=5, label="Roll")
            self.ax2.set_title("SpeedRot")
            self.line_map[line_rx] = ("speed_rot", 0, "X")
            self.line_map[line_ry] = ("speed_rot", 1, "Y")
            self.line_map[line_rz] = ("speed_rot", 2, "Z")
            self.ax2.legend(loc="upper right", fontsize="small")
        # ================= GRAPH 3 =================
        if self.rot_grav:
            x_vals = self.speed_graph
            gx = [v[0] for v in self.rot_grav]
            gy = [v[1] for v in self.rot_grav]
            gz = [v[2] for v in self.rot_grav]
            line_gx, = self.ax3.plot(x_vals, gx, marker="o", picker=5, label="Gravity (Upside Down)")
            line_gy, = self.ax3.plot(x_vals, gy, marker="o", picker=5, label="Gravity (Side)")
            line_gz, = self.ax3.plot(x_vals, gz, marker="o", picker=5, label="Unused") 
            self.ax3.set_title("RotGravR")
            self.line_map[line_gx] = ("rot_grav", 0, "X")
            self.line_map[line_gy] = ("rot_grav", 1, "Y")
            self.line_map[line_gz] = ("rot_grav", 2, "Z")
            self.ax3.legend(loc="upper right", fontsize="small")
        self.ax1.grid(True)
        self.ax2.grid(True)
        self.ax3.grid(True)    
        self.canvas.draw()

    # =====================================================
    # Drag Graph Points
    # =====================================================

    def on_pick(self, event):
        line = event.artist
        if line not in self.line_map:
            return
        self.dragging_line = line
        self.dragging_index = event.ind[0]

    def on_drag(self, event):
        if not hasattr(self, "dragging_line"):
            return
        if event.ydata is None:
            return
        line = self.dragging_line
        if line not in self.line_map:
            return  # prevents KeyError
        line_type, axis_index, axis_name = self.line_map[line]
        index = self.dragging_index
        # ================= DIFF NOSE =================
        if line_type == "diff_nose":
            self.diff_nose[index] = event.ydata
            line.set_ydata(self.diff_nose)
            param_name = f"DiffNoseVelocityR{index}"
            if param_name in self.param_widgets:
                widget = self.param_widgets[param_name]
                widget.delete(0, tk.END)
                widget.insert(0, str(round(event.ydata, 3)))
        # ================= SPEED ROT =================
        elif line_type == "speed_rot":
            self.speed_rot[index][axis_index] = event.ydata
            new_y = [v[axis_index] for v in self.speed_rot]
            line.set_ydata(new_y)
            param_name = f"SpeedRot{index}"
            if param_name in self.param_widgets:
                widget = self.param_widgets[param_name][axis_name]
                widget.delete(0, tk.END)
                widget.insert(0, str(round(event.ydata, 3)))
        # ================= ROT GRAV =================
        elif line_type == "rot_grav":
            self.rot_grav[index][axis_index] = event.ydata
            new_y = [v[axis_index] for v in self.rot_grav]
            line.set_ydata(new_y)
            param_name = f"RotGravR{index}"
            if param_name in self.param_widgets:
                widget = self.param_widgets[param_name][axis_name]
                widget.delete(0, tk.END)
                widget.insert(0, str(round(event.ydata, 3)))
        self.canvas.draw_idle()

    def on_release(self, event):
        if hasattr(self, "dragging_line"):
            del self.dragging_line
            del self.dragging_index

    # =====================================================
    # Replace PlaneID
    # =====================================================

    def replace_plane_id(self):
        if not self.file_path:
            return
        new_id = self.new_id.get().strip()
        if not new_id:
            messagebox.showwarning("Warning", "Enter New PlaneID.")
            return
        # -------------------------------------------------
        # Detect filename
        # -------------------------------------------------
        if self.uasset_path:
            full_filename = os.path.basename(self.uasset_path)
        else:
            full_filename = os.path.basename(self.file_path)
        name_without_ext = os.path.splitext(full_filename)[0]
        # Expecting: PlayerPlaneConfig_PLXXX
        prefix = "PlayerPlaneConfig_"
        if not name_without_ext.startswith(prefix):
            messagebox.showerror(
                "Error",
                "Filename does not start with PlayerPlaneConfig_"
            )
            return
        old_id = name_without_ext.replace(prefix, "")
        new_name_without_ext = prefix + new_id

        # -------------------------------------------------
        # Replace inside JSON
        # -------------------------------------------------
        with open(self.file_path, "r", encoding="utf-8") as f:
            text = f.read()
        updated_text = text.replace(old_id, new_id)
        with open(self.file_path, "w", encoding="utf-8") as f:
            f.write(updated_text)
        with open(self.file_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)
        self.original_data = copy.deepcopy(self.data)
        # -------------------------------------------------
        # If editing UASSET
        # -------------------------------------------------
        if self.uasset_path:
            try:
                # Convert JSON back to UASSET
                subprocess.run([
                    self.uassetgui_path,
                    "fromjson",
                    self.file_path,
                    self.uasset_path
                ], check=True)
                directory = os.path.dirname(self.uasset_path)
                old_uasset_path = self.uasset_path
                new_uasset_path = os.path.join(
                    directory,
                    new_name_without_ext + ".uasset"
                )
                # Rename .uasset
                os.rename(old_uasset_path, new_uasset_path)
                self.uasset_path = new_uasset_path
                # Rename .uexp
                old_uexp = old_uasset_path.replace(".uasset", ".uexp")
                new_uexp = new_uasset_path.replace(".uasset", ".uexp")
                if os.path.exists(old_uexp):
                    os.rename(old_uexp, new_uexp)
                messagebox.showinfo(
                    "Success",
                    f"PlaneID changed:\n{old_id} → {new_id}"
                )
            except Exception as e:
                messagebox.showerror("Conversion Error", str(e))
        # -------------------------------------------------
        # JSON only
        # -------------------------------------------------
        else:
            directory = os.path.dirname(self.file_path)
            new_path = os.path.join(
                directory,
                new_name_without_ext + ".json"
            )
            os.rename(self.file_path, new_path)
            self.file_path = new_path
            messagebox.showinfo(
                "Success",
                f"PlaneID changed:\n{old_id} → {new_id}"
            )


# =====================================================
# Run
# =====================================================

if __name__ == "__main__":
    root = tk.Tk()
    app = PlaneConfigEditor(root)
    root.mainloop()

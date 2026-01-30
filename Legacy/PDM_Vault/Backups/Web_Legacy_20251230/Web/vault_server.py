from flask import Flask, jsonify, render_template
import os
import time

# Folder that holds all CAD data (PRT, ASM, DRW, STEP, NEU, etc.)
VAULT_DIR = r"D:\PDM_Vault\CADData"

app = Flask(__name__)

def list_cad_files():
    """Scan vault folder for CAD files and return name + modified time."""
    allowed = (".prt", ".asm", ".drw", ".neu", ".stp", ".step")
    results = []

    for f in os.listdir(VAULT_DIR):
        full = os.path.join(VAULT_DIR, f)
        if os.path.isfile(full) and f.lower().endswith(allowed):
            results.append({
                "filename": f,
                "mtime": os.path.getmtime(full)
            })

    results.sort(key=lambda x: x["filename"].lower())
    return results


@app.route("/")
def index():
    return render_template("vault_index.html")


@app.route("/vault-files")
def vault_files():
    return jsonify(list_cad_files())


if __name__ == "__main__":
    # IMPORTANT: must be 0.0.0.0 so other machines can access the service
    app.run(host="0.0.0.0", port=5050)

import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.vm_app import vm_table, vm_stop, vm_delete

BASE_DIR = Path("/var/lib/libvirt/images/cloud-maker")

def cleanup():
  if input("Delete all vms? [y/n]: ").lower() != "y":
    return

  files = list(BASE_DIR.glob("*.qcow2")) + list(BASE_DIR.glob("*-seed.iso"))

  if not files:
    return

  names = set()
  for file in files:
    if file.name.endswith("-seed.iso"):
      names.add(file.name.removesuffix("-seed.iso"))
    else:
      names.add(file.stem)

  vms = {vm["name"]: vm["state"] for vm in vm_table()}

  for name in sorted(names):
    disk = BASE_DIR / f"{name}.qcow2"
    seed = BASE_DIR / f"{name}-seed.iso"

    if name in vms:
      if vms[name] == "running":
        vm_stop(name)

        for _ in range(30):
          time.sleep(2)
          state = next((vm["state"] for vm in vm_table() if vm["name"] == name), None)
          if state == "stopped":
            break

      if disk.exists() and seed.exists():
        vm_delete(name)
      else:
        disk.unlink(missing_ok=True)
        seed.unlink(missing_ok=True)


if __name__ == "__main__":
    cleanup()

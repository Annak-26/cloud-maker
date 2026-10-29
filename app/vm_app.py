import subprocess
from pathlib import Path
import libvirt
import tempfile

def vm_table():
  c = libvirt.open("qemu:///system")
  if c is None:
    raise RuntimeError("Connection failed.")
  try:
    vms = []
    for d in c.listAllDomains():
      vms.append({"name": d.name(), "state": "running" if d.isActive() else "stopped"})
    return vms
  finally:
    c.close()

def vm_create(name, memory=2048, vcpus=2): 
  c = libvirt.open("qemu:///system") 
  if c is None: 
    raise RuntimeError("Connection failed.")
  base_dir = Path("/var/lib/libvirt/images/cloud-maker") 
  work_dir = Path(__file__).resolve().parent.parent
  base = work_dir / "noble-server-cloudimg-amd64.img"
  disk = base_dir / f"{name}.qcow2" 
  seed = base_dir / f"{name}-seed.iso"

  try:
    try:
      c.lookupByName(name)
    except libvirt.libvirtError as e:
      if e.get_error_code() != libvirt.VIR_ERR_NO_DOMAIN:
        raise
    else:
      raise ValueError("VM already exists.")

    net = c.networkLookupByName("default")
    if not net.isActive():
      net.create()

    with tempfile.TemporaryDirectory() as tmp:
      tmp = Path(tmp)
      meta = tmp / "meta-data"
      iso = tmp / "seed.iso"
      meta.write_text(f"instance-id: {name}\nlocal-hostname: {name}\n")

      subprocess.run([
        "cloud-localds", str(iso),
        str(work_dir / "cloud-init/user-data"),
        str(meta)
      ], check=True)

      subprocess.run(["cp", str(base), str(disk)], check=True)
      subprocess.run(["qemu-img", "resize", str(disk), "10G"], check=True)
      subprocess.run(["cp", str(iso), str(seed)], check=True)

    subprocess.run([
      "virt-install",
      "--connect", "qemu:///system",
      "--name", name,
      "--memory", str(memory),
      "--vcpus", str(vcpus),
      "--import",
      "--disk", f"path={disk},format=qcow2",
      "--disk", f"path={seed},device=cdrom",
      "--os-variant", "ubuntu24.04",
      "--network", "network=default",
      "--graphics", "none",
      "--console", "pty,target_type=serial",
      "--noautoconsole"
    ], check=True, timeout=180)

    return {"name": name, "state": "running"}
  finally:
    c.close()



def vm_stop(name):
  c = libvirt.open("qemu:///system")
  if c is None:
    raise RuntimeError("Connection failed.")
  try:
    d = c.lookupByName(name)
    d.shutdown()
  finally:
    c.close()


def vm_delete(name):
  c = libvirt.open("qemu:///system")
  if c is None:
    raise RuntimeError("Connection failed.")
  try:
    d = c.lookupByName(name)
    if d.isActive():
      raise ValueError("VM must be stopped.")

    base_dir = Path("/var/lib/libvirt/images/cloud-maker")
    disk = base_dir / f"{name}.qcow2"
    seed = base_dir / f"{name}-seed.iso"

    if not disk.is_file() or not seed.is_file():
      raise ValueError("VM files not found.")

    d.undefine()
    disk.unlink()
    seed.unlink()
  finally:
    c.close()

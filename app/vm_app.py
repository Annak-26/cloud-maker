import yaml
import subprocess
from pathlib import Path
import libvirt
import tempfile
from app.img_app import img_get

MAX_VMS = 5
MAX_MEMORY = 4096
MAX_VCPUS = 4
MAX_TOTAL_MEMORY = 8192
MAX_TOTAL_VCPUS = 8


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


def vm_create(name, image="ubuntu24", memory=2048, vcpus=2, hostname=None, ssh_key=None, user_data=None): 
  c = libvirt.open("qemu:///system") 
  if c is None: 
    raise RuntimeError("Connection failed.")
  base_dir = Path("/var/lib/libvirt/images/cloud-maker") 
  work_dir = Path(__file__).resolve().parent.parent
  base = Path(img_get(image)["path"])
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
    check(c,memory,vcpus)
    net = c.networkLookupByName("default")
    if not Path("/sys/class/net/virbr0").exists():
      net.create()

    with tempfile.TemporaryDirectory() as tmp:
      tmp = Path(tmp)
      meta = tmp / "meta-data"
      user = tmp / "user-data"
      iso = tmp / "seed.iso"
      host = hostname or name

      meta.write_text(f"instance-id: {name}\nlocal-hostname: {host}\n")

      if user_data is None:
        config = yaml.safe_load((work_dir / "cloud-init/user-data").read_text()) or {}
      else:
        config = yaml.safe_load(user_data) or {}

      if not isinstance(config, dict):
        raise ValueError("Invalid user-data.")

      config["hostname"] = host

      if ssh_key:
        config.setdefault("users", ["default"])

        if "default" not in config["users"]:
          raise ValueError("user-data must include the default user.")

        config["ssh_authorized_keys"] = [ssh_key]

      user.write_text("#cloud-config\n" + yaml.safe_dump(config, sort_keys=False))

      subprocess.run([
        "cloud-localds", str(iso),
        str(user),
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


def check(c,memory,vcpus):
  d = c.listAllDomains()
  if len(d) >= MAX_VMS:
    raise ValueError("VM Limit")
  if not 512 <= memory <= MAX_MEMORY:
    raise ValueError("Memory Limit")
  if not 1 <= vcpus <= MAX_VCPUS:
    raise ValueError("VCPU Limit")
  all_memory = sum(domain.maxMemory() //1024 for domain in d)
  all_vcpus = sum(domain.info()[3] for domain in d)
  if all_memory + memory > MAX_TOTAL_MEMORY:
     raise ValueError("Total Memory Limit")
  if all_vcpus + vcpus > MAX_TOTAL_VCPUS:
     raise ValueError("Total VCPU Limit")

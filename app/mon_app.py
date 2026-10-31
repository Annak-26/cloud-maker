import time
from pathlib import Path
import libvirt


BASE_DIR = Path("/var/lib/libvirt/images/cloud-maker")


def vm_stats(name):
  c = libvirt.open("qemu:///system")
  if c is None:
    raise RuntimeError("Connection failed.")

  try:
    try:
      d = c.lookupByName(name)
    except libvirt.libvirtError as e:
      if e.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN:
        raise ValueError("Virtual machine not found.")
      raise

    if not d.isActive():
      disk = BASE_DIR / f"{name}.qcow2"
      disk_capacity = None
      disk_used = None

      if disk.exists():
        disk_used = disk.stat().st_blocks * 512 / (1024 ** 3)

        try:
          disk_capacity = domain.blockInfo(str(disk))[0] / (1024 ** 3)
        except libvirt.libvirtError:
          pass

      return {
        "name": name,
        "state": "stopped",
        "cpu_usage_percent": 0,
        "memory_allocated_mb": domain.info()[1] // 1024,
        "memory_used_mb": None,
        "disk_capacity_gb": (round(disk_capacity, 2) if disk_capacity is not None else None),
        "disk_used_gb": (round(disk_used, 2) if disk_used is not None else None)
      }


    cpu1 = d.info()[4]
    time1 = time.monotonic()
    time.sleep(1)
    cpu2 = d.info()[4]
    time2 = time.monotonic()
    cpu_usage = (cpu2 - cpu1) / ((time2 - time1) * 1e9) * 100
    d.setMemoryStatsPeriod(1)
    memory = d.memoryStats()
    memory_used = None

    if "actual" in memory and "unused" in memory:
      memory_used = (memory["actual"] - memory["unused"]) / 1024

    disk = BASE_DIR / f"{name}.qcow2"
    disk_capacity = None
    disk_used = None

    if disk.exists():
      stat = disk.stat()
      disk_used = stat.st_blocks * 512 / (1024 ** 3)

      try:
        disk_info = d.blockInfo(str(disk))
        disk_capacity = disk_info[0] / (1024 ** 3)
      except libvirt.libvirtError:
        pass

    return {
      "name": name,
      "state": "running",
      "cpu_usage_percent": round(cpu_usage, 2),
      "memory_allocated_mb": d.info()[1] // 1024,
      "memory_used_mb": round(memory_used, 2) if memory_used is not None else None,
      "disk_capacity_gb": round(disk_capacity, 2) if disk_capacity is not None else None,
      "disk_used_gb": round(disk_used, 2) if disk_used is not None else None
    }

  finally:
    c.close()

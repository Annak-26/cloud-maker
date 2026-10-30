from fastapi import FastAPI
from pydantic import BaseModel, Field
from app.vm_app import vm_table, vm_create, vm_stop, vm_delete

app = FastAPI()

class VM(BaseModel):
  name: str
  memory: int = Field(default=2048, ge=512, le=8192)
  vcpus: int = Field(default=2, ge=1, le=8)
  hostname: str | None = None
  ssh_key: str | None = None
  user_data: str | None = None

@app.get("/vms")
def get_vms():
  return vm_table()

@app.post("/vms")
def create_vm(vm: VM):
  return vm_create(vm.name, vm.memory, vm.vcpus, vm.hostname, vm.ssh_key, vm.user_data)

@app.post("/vms/{name}/stop")
def stop_vm(name: str):
  return vm_stop(name)

@app.delete("/vms/{name}")
def delete_vm(name: str):
  return vm_delete(name)

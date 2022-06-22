# Ansible DocumentDB Modules

These are drop-in modules for Ansible 2.3+ which provide the following:

- **docdb_cluster** - can create a new DocumentDB cluster or restore from a cluster snapshot
- **docdb_instance** - can create a cluster instance for an existing cluster

These modules are specifically for working with DocumentDB.

These are provided in the event they might be of use. I will not be submitting them to the Ansible project for inclusion but you are welcome to do so.

Please read the module sources for usage information. Note that not all functionality is provided but the modules are idempotent as provided.

## Example Playbook
```yaml
---

- name: Create cluster
  hosts: localhost
  connection: local

  tasks:

    - name: Launch cluster
      docdb_cluster:
        cluster_id: "new-cluster-name"
        engine: "docdb"
        state: present
        subnet_group: "my-subnet-group"
        vpc_security_group_ids: "sg-11111111111"
        wait: yes

    - name: Create DB instance
      docdb_instance:
        cluster_id: "new-cluster-name"
        instance_id: "instance-1"
        instance_type: "db.t3.medium"
        engine: "docdb"
        state: present
        region: us-east-1
        wait: yes
```
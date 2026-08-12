"""Machine-readable contracts Composer reads.

Each module pairs with a JSON document beside it and is published through a
management command, so Composer can fetch the contract for the DjangoLux
release a deployment is actually running rather than assuming one:

* :mod:`~dlux.contracts.stack` — the generated Compose topology
  (``manage.py dlux_stack_contract``)
* :mod:`~dlux.contracts.runtime` — the ``dlux_runtime`` volume layout
  (``manage.py dlux_runtime_contract``)

The command names are the cross-repo interface and are unchanged by this
grouping, which is why the move needed no alias at the old
``dlux.stack_contract`` / ``dlux.runtime_contract`` paths: nothing imported the
modules directly — not Composer, not any project.
"""

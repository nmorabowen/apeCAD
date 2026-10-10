"""Internal engine behind Document: the entity store and one handler module per op family.

Layering (imports only point down):

    dispatch   op type -> handler table
    create / edit / transform / meta   handlers, one module per op family
               (edit and transform may call create)
    topology   graph surgery shared by handlers
    state      DraftState: entities, labels, tags, id counter

Not public API. Callers use apeCAD.Document.
"""

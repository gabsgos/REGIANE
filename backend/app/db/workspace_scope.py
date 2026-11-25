"""Apply tenant boundaries to every authenticated ORM read and write."""
from fastapi import HTTPException
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session, with_loader_criteria

from backend.app.db.base import WorkspaceScoped


@event.listens_for(Session, 'do_orm_execute')
def scope_authenticated_query(state):
    workspace_id = state.session.info.get('workspace_id')
    if workspace_id is not None and (state.is_select or state.is_update or state.is_delete):
        state.statement = state.statement.options(with_loader_criteria(
            WorkspaceScoped, lambda model: model.workspace_id == workspace_id, include_aliases=True
        ))


@event.listens_for(Session, 'before_flush')
def scope_authenticated_write(session, flush_context, instances):
    workspace_id = session.info.get('workspace_id')
    if workspace_id is None:
        return
    for item in list(session.new) + list(session.dirty) + list(session.deleted):
        if not isinstance(item, WorkspaceScoped):
            continue
        previous = inspect(item).attrs.workspace_id.history.deleted
        if previous and previous[0] != workspace_id:
            raise HTTPException(status_code=403, detail='Transferencia de workspace nao permitida')
        if item in session.new and item.workspace_id is None:
            item.workspace_id = workspace_id
        if item.workspace_id != workspace_id:
            raise HTTPException(status_code=403, detail='Workspace invalido')
        for column in inspect(type(item)).columns:
            value = getattr(item, column.key)
            if value is None:
                continue
            for key in column.foreign_keys:
                target_table = key.column.table.name
                target = next((m.class_ for m in inspect(type(item)).registry.mappers
                               if m.local_table.name == target_table and issubclass(m.class_, WorkspaceScoped)), None)
                if target is not None:
                    related = session.get(target, value)
                    if related is None or related.workspace_id != workspace_id:
                        raise HTTPException(status_code=403, detail='Vinculo de outro workspace')

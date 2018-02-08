from distutils.version import StrictVersion

import six
from django import get_version as django_version
from django.db.models.fields.related import ForeignKey, OneToOneField, ManyToManyField


if StrictVersion(django_version()) >= StrictVersion('1.9'):
    from django.contrib.contenttypes.fields import GenericRelation
    from django.apps import apps
    get_models = apps.get_models
    get_apps = apps.app_configs.items
    get_app = apps.get_app_config
else:
    from django.db.models import get_models
    from django.db.models import get_apps
    from django.db.models import get_app
    try:
        from django.db.models.fields.generic import GenericRelation
        assert GenericRelation
    except ImportError:
        from django.contrib.contenttypes.generic import GenericRelation


def get_app_models_with_abstracts(app):
    appmodels = get_models(app)
    abstract_models = []
    for appmodel in appmodels:
        abstract_models = abstract_models + [abstract_model for abstract_model in appmodel.__bases__
                                             if hasattr(abstract_model, '_meta') and abstract_model._meta.abstract]
    abstract_models = list(set(abstract_models))  # remove duplicates
    return abstract_models + appmodels


def get_model_name(model):
    return model._meta.object_name


def get_full_model_list(apps, exclude_modules=set(), exclude_fields=set()):
    result = []
    for app in apps:
        result.extend(get_app_models_with_abstracts(app))

    result = list(set(result))
    if exclude_modules:
        result = list(filter(lambda model: model.__module__ not in exclude_modules, result))
    if exclude_fields:  # TODO: fields?
        result = list(filter(lambda model: get_model_name(model) not in exclude_fields, result))

    return result


def get_model_local_fields(model):
    return model._meta.local_fields


def get_model_pk_field(model):
    return model._meta.pk


def get_model_field_by_name(model, fname):
    return model._meta.get_field(fname)


def is_model_abstract(model):
    return model._meta.abstract


def get_model_abstract_fields(model):
    result = []
    for e in model.__bases__:
        if hasattr(e, '_meta') and e._meta.abstract:
            result.extend(e._meta.fields)
            result.extend(get_model_abstract_fields(e))
    return result


def get_model_m2m_fields(model):
    return model._meta.local_many_to_many


def get_m2m_through_model(m2m_field):
    return m2m_field.rel.through


def does_m2m_auto_create_table(m2m_field):
    # TODO: improve
    if getattr(m2m_field, 'creates_table', False):  # django 1.1, TODO: remove?
        return True
    through = get_m2m_through_model(m2m_field)
    if hasattr(through, '_meta') and through._meta.auto_created:  # django 1.2
        return True
    return False


def get_field_name(field, verbose=False):
    # TODO: need this function?
    return field.verbose_name if verbose and field.verbose_name else field.name


def prepare_field_old(field):
    # TODO: remove
    return {
        'field': field,  # TODO: remove
        'name': field.name,
        'type': type(field).__name__,
        'comment': field.verbose_name,  # TODO: comment?
        'primary_key': field.primary_key,
        'nullable': field.null,
        'unique': field.unique,
    }


def prepare_field(field):
    return {
        'name': field.name,
        'type': type(field).__name__,
        'comment': field.verbose_name,  # TODO: comment?
        'primary_key': field.primary_key,
        'nullable': field.null,
        'unique': field.unique,
    }


def prepare_model_fields(model):
    result = []

    # find primary key and print it first, ignoring implicit id if other pk exists
    pk = get_model_pk_field(model)
    if pk is not None:
        assert not is_model_abstract(model)
        result.append(prepare_field(pk))

    for field in get_model_local_fields(model):
        # TODO: exclude fields
        if field == pk:
            continue
        result.append(prepare_field(field))

    # TODO:
    # if self.sort_fields:
    #     result = sorted(result, key=lambda field: (not field['primary_key'], field['name']))

    return result


def get_relation_base(start_label, end_label, dotted=False):
    color = '000000'
    if start_label == '1' and end_label == '1':
        color = 'E2A639'  # TODO: themes
    if start_label == 'n' and end_label == 'n':
        color = '75A908'  # TODO: themes

    return {
        'start_label': start_label,
        'end_label': end_label,
        'dotted': dotted,
        'directional': start_label != end_label,
        'color': color,
    }


def prepare_relation(field, start_label, end_label, dotted=False):
    # TODO: handle lazy-relationships

    assert field.is_relation

    # TODO: exclude models
    # if get_model_name(target_model) in self.exclude_models:
    #     return

    r = get_relation_base(start_label, end_label, dotted=dotted)
    r.update({
        'start_obj': field.model,
        'end_obj': field.related_model,
        'start_field': field,
        'end_field': field.target_field,
    })
    return r


def prepare_m2m_through_relation(m2m_field):
    assert m2m_field.is_relation
    a = get_relation_base('n', '1')
    b = get_relation_base('n', '1')
    through = m2m_field.rel.through

    if m2m_field.rel.through_fields is not None:
        # specific fields already create relationships
        return []

    a.update({
        'start_obj': through,
        'end_obj': m2m_field.model,
        'start_field': None,  # TODO:
        'end_field': get_model_pk_field(m2m_field.model),
    })
    b.update({
        'start_obj': through,
        'end_obj': m2m_field.related_model,
        'start_field': None,  # TODO:
        'end_field': get_model_pk_field(m2m_field.related_model),
    })
    return [a, b]


def prepare_model_relations(model):
    result = []
    abstract_fields = get_model_abstract_fields(model)

    for field in get_model_local_fields(model):
        if field.attname.endswith('_ptr_id'):  # excluding field redundant with inheritance relation
            # TODO: recheck this
            continue
        if field in abstract_fields:
            # excluding fields inherited from abstract classes. they duplicate as local_fields
            continue

        # TODO: exclude fields
        # if self.get_field_name(field) in self.exclude_fields:
        #     continue

        if isinstance(field, OneToOneField):
            result.append(prepare_relation(field, '1', '1'))
        elif isinstance(field, ForeignKey):
            result.append(prepare_relation(field, 'n', '1'))
        # otherwise it's an usual field, skipping it

    for field in get_model_m2m_fields(model):
        # TODO: exclude fields
        # if self.get_field_name(field) in self.exclude_fields:
        #     continue

        if isinstance(field, ManyToManyField):
            if does_m2m_auto_create_table(field):
                result.append(prepare_relation(field, 'n', 'n'))
            else:
                result.extend(prepare_m2m_through_relation(field))
        elif isinstance(field, GenericRelation):
            result.append(prepare_relation(field, 'n', 'n', dotted=True))
        else:
            raise ValueError('Wrong m2m relation field class: {}'.format(field))

    return [rel for rel in result if rel is not None]
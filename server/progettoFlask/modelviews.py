from tkinter.ttk import Label

from flask import url_for
from flask_admin import BaseView, expose, AdminIndexView
from flask_admin.contrib import sqla
from flask_admin.model.template import ViewRowAction, EditRowAction, DeleteRowAction
from flask_login import current_user, login_required
from markupsafe import Markup
from sqlalchemy import join
from wtforms import StringField, BooleanField, SelectField, validators

import geolog
from models import db, buildings, User, professions, zones, sessionStates, rooms, digitalTwinFeed, sensorFeeds, \
    sessions, actuatorFeeds
from werkzeug.routing import ValidationError

from utilities import formatName, createABuildingtupleList

class ZoneAdmin(sqla.ModelView):
    can_edit = False
    column_list = ('city', 'state')
    column_exclude_list = [ 'lat', 'lon']
    form_columns = (
        'city',
        'state',
    )

    def on_model_delete(self, zones):
        buildingsToCheck = db.session.query(buildings).filter_by(id_zone=zones.id_zone).first()
        if buildingsToCheck is not None:
            raise ValidationError('Sono presenti strutture assegnate a questa Zona')

    def is_accessible(self):
        if current_user.is_authenticated:
            return current_user.is_admin
        else:
            return False
    def on_model_change(self, form, zones, is_created):
        if geolog.isAddressValid(formatName(str(form.city.data) + "," + str(form.state.data))):
            marker = geolog.getMarkerByType(formatName(str(form.city.data) + ',' + str(form.state.data)),
                                            "administrative")
            zones.set_lat(marker["lat"])
            zones.set_lon(marker["lon"])
            zones.city = formatName(form.city.data)
            zones.state = formatName(form.state.data)
        else:
            raise ValidationError('Indirizzo non valido')


# inserire un super user che può dare grant di permessi
class UserAdmin(sqla.ModelView):
    column_list = ('username', 'profession', 'admin', 'super_user')
    column_exclude_list = ['id', 'password']
    can_create = False
    can_delete = False
    # column_display_pk = True  # optional, but I like to see the IDs in the list
    column_hide_backrefs = False
    form_excluded_columns = ('id', 'dateOfBirth', 'password', 'profession', 'sex',)
    form_widget_args = {
        'username': {
            'disabled': True
        }
    }

    def is_accessible(self):
        if current_user.is_authenticated:
            return current_user.is_admin
        else:
            return False

    def get_list_row_actions(self):
        if current_user.is_authenticated and current_user.is_super:
            return (ViewRowAction(), EditRowAction())
        else:
            return ()

    def on_model_change(self, form, model, is_created):
        if is_created == False:
            if form.username.data == "Admin":
                raise ValidationError('Can\'t revoke permissions from Super User Admin')
            if form.super_user.data == True:
                model.admin = True
    # def get_query(self):
    #   return (self.session.query(User).join(professions,User.profession==professions.id_profession))


# TODO testing
# creazione,eliminazione e edit
class JobAdmin(sqla.ModelView):
    column_list = ('name', 'category')
    column_exclude_list = ['id_profession']
    previous_jobs = None
    form_columns = (
        'name',
        'category',)
    form_extra_fields = {
        'category': SelectField('Category',
                                choices=[(0, 'Intrattenimento'), (1, 'Studio'), (2, 'Ufficio'), (3, 'Manuale'),
                                         (4, 'Risorse umane'), (5, 'Altro')]),
    }
    def on_form_prefill(self, form, id):
        form.name.render_kw = {'readonly': True}

    def is_accessible(self):
        if current_user.is_authenticated:
            return current_user.is_admin
        else:
            return False

    def on_model_delete(self, job):
        users = db.session.query(User).filter_by(profession=job.name).first()
        if users is not None:
            raise ValidationError('Sono presenti utenti assegnati a questa professione')
        if job.name == "Administrator":
            raise ValidationError('Impossibile eliminare questa professione')


# inserimento edifici
# se non ha stanze non viene mostrato in getfree buildings
# TODO Inserimento (state,city,route,number) da calcolare(lat,lon,id_zone) da ingnorare(id_building)
# TODO Eliminazione testing
# TODO Modifica testing
# DONE Permessi di visualizzazione
class BuildingAdmin(sqla.ModelView):
    # Visible columns in the list view
    column_exclude_list = [ 'lat', 'lon']
    form_excluded_columns = ('id_building', 'address','lat', 'lon','dashboard')
    #form sarà city,address,state e basta
    form_extra_fields = {
        'state': StringField('state'),
        'route':  StringField('route'),
        'number': StringField('number'),
    }

    def _format_pay_now(view, context, model, name):
        # render a form with a submit button for student, include a hidden field for the student id
        # note how checkout_view method is exposed as a route below
        checkout_url = url_for('dashboard')

        _html = '''
            <form action="{checkout_url}" method="POST">
                <input id="building_id" name="building_id"  type="hidden" value="{building_id}">
                <button type='submit'>Dashboard</button>
            </form
        '''.format(checkout_url=checkout_url, building_id=model.id_building)

        return Markup(_html)

    column_formatters = {
        'dashboard': _format_pay_now
    }
    def is_accessible(self):
        if current_user.is_authenticated:
            return current_user.is_admin
        else:
            return False
    def on_form_prefill(self, form, id):
        building = db.session.query(buildings).filter_by(id_building=id).first()
        zone_candidates = db.session.query(zones).filter_by(city=building.city)
        zone= geolog.geoNearest(zone_candidates, building)
        form.state.data=zone.state
    def on_model_change(self, form, building, is_created):
        if form.city.data is None:
            raise ValidationError('Indirizzo non valido')
        if form.state.data is None:
            raise ValidationError('Indirizzo non valido')
        street = ""
        if form.route.data is not None and form.route.data != '':
            if form.number.data is not None:
                street = formatName(form.route.data + " " + form.number.data)
            else:
                street = formatName(form.route.data)
        marker = geolog.geoMarker(formatName(form.city.data),street,formatName(form.state.data))
        if marker is None:
            raise ValidationError('Indirizzo non valido')
        else:
            building.city=formatName(form.city.data)
            building.lon = marker['lon']
            building.lat = marker['lat']
            building.address = marker['route'] + " ("+formatName(form.state.data)+")"
            building.set_availability(form.available.data)
        zone = db.session.query(zones).filter_by(city=formatName(form.city.data)).filter_by(state=formatName(form.state.data)).first()
        if zone is None:
            zone =  zones(formatName(form.city.data),formatName(form.state.data))
            db.session.add(zone)
            db.session.commit()
    # aggiungere logica
    # se sessioni attive non s'inserisce nienete
    def on_model_delete(self, building):
        activeSessionStates = db.session.query(sessionStates.id_room).filter_by(active=True).first()
        activeRoom = db.session.query(rooms).filter_by(id_building=building.id_building).filter(rooms.id_room.in_(activeSessionStates)).first()
        if activeRoom is not None:
            raise ValidationError('Sono presenti sessioni attive in questo Edificio')
        else:
            rooms_to_delete = db.session.query(rooms).filter_by(id_building=building.id_building)
            for room in rooms_to_delete:
                digital_twins_to_delete=db.session.query(digitalTwinFeed).filter_by(id_room=room.id_room)#ok
                sensorfeed_to_delete=db.session.query(sensorFeeds).filter_by(id_room=room.id_room)#ok
                session_states_to_delete = db.session.query(sessionStates).filter_by(id_room=room.id_room)#ok
                session_ids_states_to_delete= db.session.query(sessionStates.id_session).filter_by(id_room=rooms.id_room)#ok
                sessions_to_delete = db.session.query(sessions).filter(sessions.id.in_(session_ids_states_to_delete))#ok
                actuator_feeds_to_delete=db.session.query(actuatorFeeds).filter(actuatorFeeds.id_session.in_(session_ids_states_to_delete))#ok1
                actuator_feeds_to_delete.delete(synchronize_session='fetch')
                sessions_to_delete.delete(synchronize_session='fetch')
                session_states_to_delete.delete(synchronize_session='fetch')
                sensorfeed_to_delete.delete(synchronize_session='fetch')
                digital_twins_to_delete.delete(synchronize_session='fetch')
                rooms_to_delete.delete(synchronize_session='fetch')
                db.session.commit()


# DONE convertire profession alla stringa
# DONE mettere il controllo d'inserimento della zona
# TODO inserimento palazzi
# TODO inserimento stanza/digitaltwin


class MyView(BaseView):
    @expose('/')
    @login_required
    def index(self):
        return self.render('admin/index.html')


class MyHomeView(AdminIndexView):
    @expose('/')
    @login_required
    def index(self):
        arg1 = 'Hello'
        return self.render('admin/index.html')



#TODO testing inserimento, eliminazione e modifica



#creazione edifici

#grant permessi admin
#TODO gestione del digitaltwin per l'eliminazione delle stanze
#all'eliminazione togliamo pure i digital twin
#si blocca se ci sono sessioni attive
#alla creazione non viene creato nessun digital twin
#per la creazione possiamo assegnare una città già esistente o di poter inserire
#una città nuova
#modifica dell'indirizzo, con aggiornamento dei dati e controllo validità dell'indirizzo




#TODO testing eliminazione a cascata
#TODO testing creazione e edit
#TODO gestione del digitalTwin
#DONE gestione accessibilità
#inserimento,modifica ed eliminazione stanze
#gestione del digital twin
class RoomAdmin(sqla.ModelView):
    column_list = ('id_room','description','available','dashboard')
    form_extra_fields = {
        'room':StringField('room'),
        'buildings': SelectField('buildings',coerce=int,validate_choice=False, choices=[]),
    }

    form_columns = ('room','buildings','available')
    def _format_pay_now(view, context, model, name):
        # render a form with a submit button for student, include a hidden field for the student id
        # note how checkout_view method is exposed as a route below
        checkout_url = url_for('dashboard')

        _html = '''
            <form action="{checkout_url}" method="POST">
                <input id="building_id" name="building_id"  type="hidden" value="{building_id}">
                <button type='submit'>Dashboard</button>
            </form
        '''.format(checkout_url=checkout_url, building_id=model.id_building)

        return Markup(_html)

    column_formatters = {
        'dashboard': _format_pay_now
    }
    def on_form_prefill(self, form, id):
        #with app.app_context():
            room = db.session.query(rooms).filter_by(id_room=id).first()
            form.room.render_kw = {'disabled': True}
            form.room.data=room.id_room
            buildingsForForm = db.session.query(buildings)
            choices = createABuildingtupleList(buildingsForForm)
            form.buildings.choices = choices
    def create_form(self,obj=None):
       form = super(RoomAdmin, self).create_form(obj=obj)
       form.room.render_kw = {'disabled': True}
       form.room.data = "(Data not required)"
       buildingsForForm = db.session.query(buildings)
       choices=createABuildingtupleList(buildingsForForm)
       form.buildings.choices = choices
       return form

    def is_accessible(self):
        if current_user.is_authenticated:
            return current_user.is_admin
        else:
            return False
    def on_model_change(self, form, room, is_created):
        if not is_created:
            activeSessionStates = db.session.query(sessionStates.id_room).filter_by(active=True, id_room=room.id_room).first()
            if activeSessionStates is not None:
                raise ValidationError('è presente una sessione attiva in questa stanza!')
            else:
                room.set_building(form.buildings.data)
                building=db.session.query(buildings).filter_by(id_building=form.buildings.data).first()
                room.description = "Room of building id:"+str(form.buildings.data)+ " stationed at "+building.city + " " +building.address
                room.set_availability(form.available.data)
        else:
            room.set_building(form.buildings.data)
            building = db.session.query(buildings).filter_by(id_building=form.buildings.data).first()
            room.description = "Room of building id:" + str(form.buildings.data) + " stationed at " + building.city + " " + building.address
            room.set_availability(form.available.data)
    def on_model_delete(self, room):
        activeSessionState = db.session.query(sessionStates).filter_by(active=True).filter_by(id_room=room.id_room).first()
        if activeSessionState is not None:
            raise ValidationError('E\' presente una sessione attiva in questa stanza')
        else:
            digital_twins_to_delete = db.session.query(digitalTwinFeed).filter_by(id_room=room.id_room)  # ok
            sensorfeed_to_delete = db.session.query(sensorFeeds).filter_by(id_room=room.id_room)  # ok
            session_states_to_delete = db.session.query(sessionStates).filter_by(id_room=room.id_room)  # ok
            session_ids_states_to_delete = db.session.query(sessionStates.id_session).filter_by(id_room=rooms.id_room)  # ok
            sessions_to_delete = db.session.query(sessions).filter(sessions.id.in_(session_ids_states_to_delete))  # ok
            actuator_feeds_to_delete = db.session.query(actuatorFeeds).filter(actuatorFeeds.id_session.in_(session_ids_states_to_delete))  # ok1
            actuator_feeds_to_delete.delete(synchronize_session='fetch')
            sessions_to_delete.delete(synchronize_session='fetch')
            session_states_to_delete.delete(synchronize_session='fetch')
            sensorfeed_to_delete.delete(synchronize_session='fetch')
            digital_twins_to_delete.delete(synchronize_session='fetch')
            db.session.commit()

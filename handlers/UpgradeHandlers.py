# -*- coding: utf-8 -*-
'''
Created on Sep 25, 2012

@author: moloch

    Copyright 2012 Root the Box

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
----------------------------------------------------------------------------

This file contains the "Upgrade Handlers", access to these handlers can
be purchased from the "Black Market" (see markethandlers.py)

'''


import logging

from BaseHandlers import BaseHandler
from models import dbsession, User, WallOfSheep, Team, Box, SourceCode
from libs.Form import Form
from libs.SecurityDecorators import authenticated, has_item, debug
from mimetypes import guess_type
from base64 import b64decode


class PasswordSecurityHandler(BaseHandler):
    ''' Renders views of items in the market '''

    @authenticated
    @has_item("Password Security")
    def get(self, *args, **kwargs):
        ''' Render update hash page '''
        self.render_page()

    @authenticated
    @has_item("Password Security")
    def post(self, *args, **kwargs):
        ''' Attempt to upgrade hash algo '''
        form = Form(
            old_password="Enter your existing password",
            new_password1="Enter a new password",
            new_password2="Confirm your new password",
        )
        if form.validate(self.request.arguments):
            user = self.get_current_user()
            passwd = self.get_argument('new_password1')
            old_passwd = self.get_argument('old_password')
            if not user.validate_password(old_passwd):
                self.render_page(["Invalid password"])
            elif not passwd == self.get_argument('new_password2'):
                self.render_page(["New passwords do not match"])
            elif user.team.money < self.config.password_upgrade:
                self.render_page(["You cannot afford to upgrade your hash"])
            elif len(passwd) <= self.config.max_password_length:
                user.team.money -= self.config.password_upgrade
                dbsession.add(user.team)
                dbsession.flush()
                self.update_password(passwd)
                self.render_page()
            else:
                self.render_page(["New password is too long"])
        else:
            self.render_page(form.errors)

    def render_page(self, errors=None):
        user = self.get_current_user()
        self.render('upgrades/password_security.html',
            errors=errors, user=user, cost=self.config.password_upgrade,
        )

    def update_password(self, new_password):
        '''
        Update user to new hashing algorithm and then updates the password
        using the the new algorithm
        '''
        user = self.get_current_user()
        user.algorithm = user.next_algorithm()
        dbsession.add(user)
        dbsession.flush()
        user.password = new_password
        dbsession.add(user)
        dbsession.flush()


class FederalReserveHandler(BaseHandler):

    @authenticated
    @has_item("Federal Reserve")
    def get(self, *args, **kwargs):
        user = self.get_current_user()
        self.render('upgrades/federal_reserve.html', user=user)


class FederalReserveAjaxHandler(BaseHandler):

    @authenticated
    @has_item("Federal Reserve")
    def get(self, *args, **kwargs):
        commands = {
            'ls': self.ls,          # Query
            'info': self.info,      # Report
            'xfer': self.transfer,  # Transfer
        }
        if 0 < len(args) and args[0] in commands:
            commands[args[0]]()
        else:
            self.write({'error': 'No argument'})
            self.finish()

    @authenticated
    @has_item("Federal Reserve")
    def post(self, *args, **kwargs):
        self.get(*args, **kwargs)

    @debug
    def ls(self):
        if self.get_argument('data').lower() == 'accounts':
            self.write({'accounts': [team.name for team in Team.all()]})
        elif self.get_argument('data').lower() == 'users':
            data = {}
            for user in User.all_users():
                data[user.handle] = {
                    'account': user.team.name,
                    'algorithm': user.algorithm,
                    'password': user.password,
                }
            self.write({'users': data})
        else:
            self.write({'Error': 'Invalid data type'})
        self.finish()

    @debug
    def info(self):
        team_name = self.get_argument('account')
        team = Team.by_name(team_name)
        if team is not None:
            self.write({
                'name': team.name,
                'balance': team.money,
                'users': [user.handle for user in team.members]
            })
        else:
            self.write({'error': 'Account does not exist'})
        self.finish()

    @debug
    def transfer(self):
        user = self.get_current_user()
        source = Team.by_name(self.get_argument('source', ''))
        destination = Team.by_name(self.get_argument('destination', ''))
        try:
            amount = int(self.get_argument('amount', 0))
        except ValueError:
            amount = 0
        victim_user = User.by_handle(self.get_argument('user', None))
        password = self.get_argument('password', '')
        user = self.get_current_user()
        # Validate what we got from the user
        if source is None:
            self.write({"error": "Source account does not exist"})
        elif destination is None:
            self.write({"error": "Destination account does not exist"})
        elif victim_user is None or not victim_user in source.members:
            self.write({"error": "User is not authorized for this account"})
        elif victim_user in user.team.members:
            self.write({"error": "You cannot steal from your own team"})
        elif not 0 < amount <= source.money:
            self.write({
                "error": "Invalid transfer amount; must be greater than 0 and less than $%d" % source.money
            })
        elif destination == source:
            self.write({
                "error": "Source and destination are the same account"
            })
        elif victim_user.validate_password(password):
            logging.info("Transfer request from %s to %s for $%d by %s" % (
                source.name, destination.name, amount, user.handle
            ))
            xfer = self.theft(victim_user, destination, amount)
            self.write({
                "success":
                "Confirmed transfer to '%s' for $%d (after 15%s commission)" % (destination.name, xfer, '%',)
            })
        else:
            self.write({"error": "Incorrect password for account, try again"})
        self.finish()

    def theft(self, victim, destination, amount):
        ''' Successfully cracked a password '''
        victim.team.money -= abs(amount)
        value = int(abs(amount) * 0.85)
        password = self.get_argument('password', '')
        destination.money += value
        dbsession.add(destination)
        dbsession.add(victim.team)
        user = self.get_current_user()
        sheep = WallOfSheep(
            preimage=unicode(password),
            cracker_id=user.id,
            victim_id=victim.id,
            value=value,
        )
        dbsession.add(sheep)
        dbsession.flush()
        self.event_manager.cracked_password(user, victim, password, value)
        return value


class SourceCodeMarketHandler(BaseHandler):

    @authenticated
    @has_item("Source Code Market")
    def get(self, *args, **kwargs):
        self.render_page()

    @authenticated
    @has_item("Source Code Market")
    def post(self, *args, **kwargs):
        form = Form(box_uuid="Please select leaked code to buy")
        if form.validate(self.request.arguments):
            box = Box.by_uuid(self.get_argument('box_uuid', ''))
            if box is not None and box.source_code is not None:
                user = self.get_current_user()
                if box.source_code.price <= user.team.money:
                    self.purchase_code(box)
                    self.redirect("/source_code_market")
                else:
                    self.render_page(["You cannot afford to purchase this code"])
            else:
                self.render_page(["Box does not exist"])
        else:
            self.render_page(form.errors)

    def purchase_code(self, box):
        ''' Modify the database to reflect purchase '''
        team = self.get_current_user().team
        source_code = SourceCode.by_box_id(box.id)
        team.money -= abs(source_code.price)
        team.purchased_source_code.append(source_code)
        logging.info("%s purchased '%s' from the source code market." % 
            (team.name, source_code.file_name,)
        )
        dbsession.add(team)
        dbsession.flush()

    def render_page(self, errors=None):
        ''' Addes extra params to render() '''
        user = self.get_current_user()
        boxes = filter(lambda box: box.source_code is not None, Box.all())
        self.render('upgrades/source_code_market.html', 
            user=user, boxes=boxes, errors=errors
        )


class SourceCodeMarketDownloadHandler(BaseHandler):
    ''' Allows users to download files they have purchased '''

    @authenticated
    @has_item("Source Code Market")
    def get(self, *args, **kwargs):
        uuid = self.get_argument('uuid', '', strip=True)
        box = Box.by_uuid(uuid)
        if box is not None and box.source_code is not None:
            user = self.get_current_user()
            if box.source_code in user.team.purchased_source_code:
                root = self.application.settings['source_code_market_dir']
                src_file = open(str(root + '/' + box.source_code.uuid), 'r')
                src_data = b64decode(src_file.read())
                src_file.close()
                content_type = guess_type(box.source_code.file_name)[0]
                if content_type is None: content_type = 'unknown/data'
                self.set_header('Content-Type', content_type)
                self.set_header('Content-Length', len(src_data))
                self.set_header('Content-Disposition', 
                    'attachment; filename=%s' % box.source_code.file_name
                )
                self.write(src_data)
                self.finish()
            else:
                self.render('public/404.html')
        else:
            self.render('public/404.html')


class SwatHandler(BaseHandler):
    ''' Allows users to bribe admins '''

    @authenticated
    @has_item("SWAT")
    def get(self, *args, **kwargs):
        self.render('upgrades/swat.html', errors=None)

    @authenticated
    @has_item("SWAT")
    def post(self, *args, **kwargs):
        form = Form(
            uuid="Please select a target to SWAT",
        )
        if form.validate(self.request.arguments):
            target = User.by_uuid(self.get_argument('uuid', strip=True))
            if target is not None:
                user = self.get_current_user()
                try:
                    #bribe = abs(int(self.get_argument('bribe', 'Nan')))
                    if bribe < user.team.money:
                        pass
                    else:
                        self.render('upgrades/swat.html',
                            errors=["You cannot afford a bribe this large"]
                        )
                except ValueError:
                    self.render('upgrades/swat.html', 
                        errors=["Invalid bribe amount, must be a number"]
                    )
            else:
                self.render('upgrades/swat.html', 
                    errors=["Target user does not exist"]
                )
        else:
            self.render('upgrades/swat.html', errors=form.errors)

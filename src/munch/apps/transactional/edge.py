import logging

from django.core.signals import request_started
from django.core.signals import request_finished
from slimta.edge.smtp import SmtpEdge
from slimta.edge.smtp import SmtpValidators
from slimta.util.proxyproto import ProxyProtocol
from slimta.util.proxyproto import ProxyProtocolV1
from slimta.util.proxyproto import ProxyProtocolV2
from slimta.util.proxyproto import LocalConnection
from slimta.util.proxyproto import invalid_pp_source_address

from munch.apps.users.models import SmtpApplication

log = logging.getLogger(__name__)


class EdgeValidators(SmtpValidators):
    def handle_auth(self, reply, creds):
        # Force authentication over TLS
        if not self.session.security:
            reply.code = '530'
            reply.message = '5.7.0 Must issue a STARTTLS command first'
            return

        authenticated = False
        application = SmtpApplication.objects.filter(
            username=creds.authcid, author__is_active=True).only(
                'secret').first()
        if application:
            authenticated = creds.check_secret(application.secret)
            if authenticated:
                log.info('Successfull login from "{}"'.format(creds.authcid))

        if not authenticated:
            reply.code = '535'
            reply.message = '5.7.8 Authentication credentials invalid'
            log.warning('Failed login from "{}" (wrong credentials)'.format(
                creds.authcid))

    def handle_mail(self, reply, sender, params):
        # Make authentication mandatory
        if not hasattr(self.session, 'auth') or not self.session.auth:
            reply.code = '535'
            reply.message = '5.7.0 Authentification is required'
            log.warning('Unauthenticated traffic from {} refused'.format(
                self.session.address[0]))


class TransactionalSmtpEdge(SmtpEdge):
    """ Default Transactional Smtp Edge """
    def handle(self, socket, address):
        """ Just overwrite the handle to have database lock per connection """
        log.info('Incoming connection from {}:{}'.format(
            address[0], address[1]))
        request_started.send(
            sender='transactional-edge-{}-{}'.format(address[0], address[1]))
        super().handle(socket, address)
        request_finished.send(
            sender='transactional-edge-{}-{}'.format(address[0], address[1]))


class ProxyProtocolTransactionalSmtpEdge(
        ProxyProtocol, TransactionalSmtpEdge):
    """ Proxy protocol compatible Smtp Edge based on TransactionalSmtpEdge """
    def handle(self, socket, address):
        """
        This method is mostly copy-paste from Slimta to be able to handle
        remote ip retrieved before calling TransactionalSmtpEdge.handle method
        """
        try:
            initial = self._ProxyProtocol__read_pp_initial(socket)
            if initial.startswith(b'PROXY '):
                address, _ = ProxyProtocolV1.process_pp_v1(socket, initial)
            elif initial == b'\r\n\r\n\x00\r\nQ':
                address, _ = ProxyProtocolV2.process_pp_v2(socket, initial)
            else:
                raise AssertionError('Invalid proxy protocol signature')
        except LocalConnection:
            log.error(
                "Parsed proxy protocol header si for local "
                "connection, and should not be proxied.")
            return
        except AssertionError as exc:
            log.error(
                'Error while retrieving ProxyProto '
                'address: {} ({})'.format(socket, str(exc)))
            address = invalid_pp_source_address
        else:
            log.debug(
                'Successfully retrieve ProxyProto address: {}:{}'.format(
                    address[0], address[1]))
        super(TransactionalSmtpEdge, self).handle(socket, address)

import logging

from cryptojwt import as_unicode
from cryptojwt.jws.jws import factory
from oidcendpoint.oidc import registration
from oidcmsg.oidc import RegistrationRequest

from fedservice.entity_statement.collect import branch2lists
from fedservice.entity_statement.policy import diff2policy
from fedservice.entity_statement.utils import create_authority_hints
from fedservice.entity_statement.verify import eval_chain

logger = logging.getLogger(__name__)


class Registration(registration.Registration):
    request_format = 'jose'
    request_placement = 'body'
    response_format = 'jose'

    def __init__(self, endpoint_context, **kwargs):
        registration.Registration.__init__(self, endpoint_context, **kwargs)
        self.post_construct.append(self.create_entity_statement)

    def parse_request(self, request, auth=None, **kwargs):
        return request

    def process_request(self, request=None, **kwargs):
        """

        :param request: An entity statement in the form of a signed JT
        :param kwargs:
        :return:
        """
        _fe = self.endpoint_context.federation_entity

        request = as_unicode(request)
        _jwt = factory(request)
        payload = _jwt.jwt.payload()

        # collect trust chains
        _tree = _fe.collect_statement_chains(payload['iss'], payload)
        _node = {payload['iss']: (request, _tree)}
        _chains = branch2lists(_node)
        # verify the trust paths
        statements = [eval_chain(c, _fe.key_jar, 'openid_relying_party') for c in _chains]

        _fe.proposed_authority_hints = create_authority_hints(
            _fe.authority_hints, statements)

        statement = _fe.pick_metadata(statements)

        # handle the registration request as in the non-federation case.
        req = RegistrationRequest(**statement.metadata)
        response_info = registration.Registration.process_request(
            self, req, authn=None, **kwargs)
        if "response_args" in response_info:
            _policy = diff2policy(response_info['response_args'],
                                  payload['metadata'][_fe.opponent_entity_type])
            entity_statement = _fe.create_entity_statement(
                _fe.entity_id,
                payload['iss'],
                _fe.key_jar,
                metadata={'federation_entity': {"trust_anchor_id": statement.fo}},
                metadata_policy={_fe.opponent_entity_type: _policy},
                aud=payload['iss']
            )
            response_info["response_msg"] = entity_statement
            del response_info["response_args"]

        return response_info

    @staticmethod
    def create_entity_statement(response_args, request, endpoint_context,
                                **kwargs):
        """
        wrap the non-federation response in a federation response

        :param response_args:
        :param request:
        :param endpoint_context:
        :param kwargs:
        :return:
        """
        _fe = endpoint_context.federation_entity
        _md = {_fe.opponent_entity_type: response_args.to_dict()}
        return _fe.create_entity_statement(_fe.entity_id, sub=_fe.entity_id,
                                           metadata=_md,
                                           authority_hints=_fe.proposed_authority_hints)

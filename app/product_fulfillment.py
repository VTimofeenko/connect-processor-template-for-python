import re
from connect.resources import FulfillmentAutomation
from datetime import datetime
from app.api_client.isv_client import APIClient
from app.utils.logger import logger, function_log
from app.utils.utils import Utils
from app.utils.globals import Globals
from connect.exceptions import FailRequest, SkipRequest, InquireRequest
from app.utils.message import Message
from connect.models import Param, ActivationTemplateResponse, Fulfillment, ActivationTileResponse


class ProductFulfillment(FulfillmentAutomation):

    # This method processes the fulfilment requests of Pending status for all the actions
    # Returns Activation response to Connect which updates the status of fulfilment request as well as Subscription
    @function_log
    def process_request(self, req: Fulfillment) -> object:
        # The req, parameter of process_request, is an object for Fulfilment request for the Subscription in Connect
        try:
            logger.info(f"##### Processing Request: {req.id} for subscription: {req.asset.id} starts. ########")
            logger.debug(f"Fulfillment request: {Utils.serialize(req, restrict=True)}")

            # Checking the type of Subscription from Connect
            if req.type == 'purchase':
                # Type PURCHASE means, it is a new subscription in Connect
                return self.purchase(req=req, automation=self)
            if req.type == 'change':
                # Type CHANGE means, it is a change request of an existing active subscription in Connect
                # Change request includes request for changing the quantity of subscribed item/SKU
                # or adding more items
                return self.change(req=req, automation=self)
            if req.type == 'suspend':
                # Type SUSPEND means, it is a suspend request of an existing active subscription in Connect
                return self.suspend(req=req, automation=self)
            if req.type == 'resume':
                # Type RESUME means, it is a resume request of an existing suspended subscription in Connect
                return self.resume(req=req, automation=self)
            if req.type == 'cancel':
                # Type CANCEL means, it is a cancel request of an existing subscription in Connect
                return self.cancel(req=req, automation=self)


        except SkipRequest as err:
            logger.warning(Globals.SKIP_ACTION + str(err))
            raise err
        except FailRequest as err:
            logger.error(f"Issue while processing request. Error: {str(err)}")
            raise err

    # This method processes the fulfilment request for creating new subscription
    # Returns Activation response template configured in Connect and updates the status of fulfilment request as well as Subscription
    @function_log
    def purchase(self, req, automation: FulfillmentAutomation):
        logger.info(f"*** Processing PURCHASE method for request {req.id} ***")

        # Validate Ordering parameters.
        # Ordering parameters could be used in API payload to create subscription in Vendor system.
        # self.check_order_parameters(req)
        # If validation fails, this method raise Inquire request with appropriate message to get proper information.

        # If validation is successful then proceed

        # If the customer creation action or API is separate from subscription creation, then introduce a method for customer creation.
        # self.create_customer(req)

        # Create subscription
        subscription_info = self._create_subscription(automation, req)

        # If none of the SkipRequest, InquireRequst or FailRequest was raised, means that the provisioning was successful.
        # Approve the Fulfilment request by returning the Activation template
        # Approve is the final status of the Fulfilment Request of Subscription in Connect
        try:
            return self.activate_template(req=req, template_type='activationTemplate')
            # Returning the Activation Template will update the status of Fulfilment Request object to Approved and Subscription object status to Active.
            # The statuses will not get updated as Approved/Active if any of the mandatory/required fulfilment parameter in Fulfilment Request remain empty.

        except SkipRequest as skip:
            raise skip
        except FailRequest as err:
            logger.error(Message.Shared.ACTIVATING_TEMPLATE_ERROR.format(str(err.message)))
            # The Fulfilment Request was provisioned successfully, but Activation template could not be returned successfully.
            # Therefore, we log the error message and do not fail the request
            raise SkipRequest(Message.Shared.ACTIVATING_TEMPLATE_ERROR.format(str(err.message)))
        except Exception as ex:
            logger.error(Message.Shared.ACTIVATING_TEMPLATE_ERROR.format(str(ex)))
            raise SkipRequest(Message.Shared.ACTIVATING_TEMPLATE_ERROR.format(str(ex)))

    # This method is responsible to make the Vendor API calls to create the subscription
    @function_log
    def _create_subscription(self, automation, req):

        try:
            # Preparing payload for Create Subscription Vendor API
            data = self._parse_subscription(req)

            # Get the Vendor API credentials.
            # Here, the Vendor API credentials are being fetched from the configuration parameter set for a Product in Connect Vendor Portal
            # The location to save Vendor API credentials can be as desired. Customize to fetch data accordingly.
            credentials = Utils.get_credentials(req.marketplace.id, req.asset.configuration, req.asset.connection.type)

            # Initiating the API client
            api_client = APIClient(credentials)

            # Send payload (data) to make the Vendor API call for creating subscription
            subscription_info = api_client.create_subscription(data=data)

            # Check if the API call was successful and save the response data in Connect
            if subscription_info['tenantId']:
                logger.info('Subscription created.')

                # Save the info in the response as fulfilment parameters for Subscription in Connect

                # The id of param should match with the id of one of the fulfilment parameter
                params = [
                        Param(id='subscriptionId', value=subscription_info['tenantId'])
                ]
                # Update the fulfilment parameters in Fulfilment Request in Connect with the corresponding value
                automation.update_parameters(req.id, params)

            else:
                # If API call returned error, Raise the concerned action accordingly
                if subscription_info['errors'][0].get('errorCode') is None \
                        or subscription_info['errors'][0].get('errorCode') == 'UNKNOWN_ERROR':
                    logger.error(Globals.SKIP_ACTION + subscription_info['errors'][0].get('errorMessage'))
                    # Since the error was unknown, the request will be skipped to be attempted again later
                    raise SkipRequest(subscription_info['errors'][0].get('errorMessage'))
                else:
                    # Fail the Fulfilment request and provide error message in API response
                    raise FailRequest(subscription_info['errors'][0].get('errorMessage'))

        except FailRequest as err:
            logger.error(Globals.FAIL_ACTION + str(err))
            # Fail the Fulfilment request if any issue encountered in the above try block
            # Add proper validations and handle boundary and corner cases appropriately to avoid failure.
            raise err
        return subscription_info

    # This method is responsible to construct payload/body required to make the Vendor API call to create/change the subscription
    @function_log
    def _parse_subscription(self, req):
        logger.info("Parsing subscription {}".format(req.asset.external_id))

       # Preparing API payload/body json
        # The data needs to be as per the schema requirement of Vendor API

        data = {}

        # The following is the example of how to use data from req in the payload body
        # data = {
        #     "company": {
        #         "name": request.asset.tiers.customer.name,
        #         "address": request.asset.tiers.customer.contact_info.address_line1,
        #         "city": request.asset.tiers.customer.contact_info.city,
        #         "state": request.asset.tiers.customer.contact_info.state,
        #         "postal_code": request.asset.tiers.customer.contact_info.postal_code,
        #         "country": request.asset.tiers.customer.contact_info.country,
        #         "note": "",
        #         "emergency_email": request.asset.get_param_by_id('customer_admin_email').value
        #     },
        #     "user": {
        #         # "login_name": request.asset.get_param_by_id('login_name').value,
        #         "login_name": login_name,
        #         "first_name": request.asset.tiers.customer.contact_info.contact.first_name,
        #         "last_name": request.asset.tiers.customer.contact_info.contact.last_name,
        #         "phone": {
        #             "area_code": request.asset.tiers.customer.contact_info.contact.phone_number.area_code,
        #             "number": request.asset.tiers.customer.contact_info.contact.phone_number.phone_number,
        #             "extension": request.asset.tiers.customer.contact_info.contact.phone_number.extension
        #         },
        #         "email": request.asset.get_param_by_id('customer_admin_email').value,
        #         "time_zone": "Pacific Standard Time",
        #         "language": "en-US"
        #     }
        # }

        return data

    # This method processes the fulfilment request for updating existing subscription
    @function_log
    def change(self, req, automation: FulfillmentAutomation):
        logger.info(f"*** Processing CHANGE method for request {req.id} ***")

        # If the business does not support downsize, check if any item quantity is reduced.
        # If yes, fail the request with proper message.
        self.check_if_downsize(req)
        logger.info(f"Operation requested is not a downsize.")

        # Process the request to change the subscription
        self._change_subscription(automation, req)

        # If none of the SkipRequest, InquireRequst or FailRequest was raised, means that the provisioning was successful.
        # Approve the Fulfilment Request by sending back the Activation template
        # Approve is the final status of the Fulfilment Request

        try:
            # Returning the Activation Template will update the status of Fulfilment Request object to Approved and Subscription object status remains Active.
            # The statuses will not get updated as Approved/Active if any of the mandatory/required fulfilment parameter in Fulfilment Request remain empty.
            return self.activate_template(req=req, template_type='activationTemplate')
            # If required, another template can be created and configured in Vendor Protal. Use the template name for template_type
        except SkipRequest as skip:
            raise skip
        except FailRequest as err:
            logger.error(Globals.SKIP_ACTION + Message.Shared.ACTIVATING_TEMPLATE_ERROR.format(str(err.message)))
            # The Fulfilment Request was provisioned successfully, but Activation template could not be returned successfully.
            # Therefore, we log the error message and do not fail the request
            raise SkipRequest(Message.Shared.ACTIVATING_TEMPLATE_ERROR.format(str(err.message)))
        except Exception as ex:
            logger.error(Globals.SKIP_ACTION + Message.Shared.ACTIVATING_TEMPLATE_ERROR.format(str(ex)))
            raise SkipRequest(Message.Shared.ACTIVATING_TEMPLATE_ERROR.format(str(ex)))

    # This method checks if the change request is a downsize. If yes, fails the request. This can be a requirement if refund is not allowed.
    @staticmethod
    @function_log
    def check_if_downsize(req):
        if Utils.is_downsize_request(req.asset.items):
            logger.error(Globals.FAIL_ACTION + Message.Shared.NOT_ALLOWED_DOWNSIZE)
            raise FailRequest(Message.Shared.NOT_ALLOWED_DOWNSIZE)

    # This method is responsible to make the Vendor API calls to update a subscription
    @function_log
    def _change_subscription(self, automation, req):
        try:
            logger.info(f"Changing subscription")

            # Get the existing subscription Id saved as fulfilment parameter
            subscriptionId = req.asset.get_param_by_id('subscriptionId').value

            # Prepare the body/payload for the Vendor API to update the subscription
            data = self._parse_subscription(req=req)

            # Get the Vendor API credentials.
            # Here, the Vendor API credentials are being fetched from the configuration parameter set for a Product in Connect Vendor Portal
            # The location to save Vendor API credentials can be as desired. Customize to fetch data accordingly.
            credentials = Utils.get_credentials(req.marketplace.id, req.asset.configuration, req.asset.connection.type)

            # Initiating the API client
            api_client = APIClient(credentials)

            # Send payload (data) to make the Vendor API call for changing subscription
            operation_result = api_client.change_subscription(data, subscriptionId)

            # Check if the API call was successful and save the response data in Connect
            logger.debug('Change Subscription response: {}'.format(Utils.serialize(operation_result)))
            self._check_update_response(automation, operation_result, req)

        except FailRequest as err:
            logger.error(Globals.FAIL_ACTION + str(err))
            raise err

    @function_log
    def _check_update_response(self, automation, operation_result, req):
        logger.info(f"Checking update response")
        if Utils.get_status_code(operation_result).lower() == 'success':
            logger.info('Subscription changed.')
            now = datetime.now()
            params = [
                      Param(id='creationDate', value=now),
                      ]
            automation.update_parameters(req.id, params)

        else:
            logger.warning(f"Subscription has not changed")
            # If API call returned error, Raise the concerned action accordingly
            if "errors" in operation_result:
                if operation_result['errors'][0].get('errorCode') is None \
                        or operation_result['errors'][0].get('errorCode') == 'UNKNOWN_ERROR':
                    logger.warning(operation_result['errors'][0].get('errorMessage'))
                    # Since the error was unknown, the request will be skipped to be attempted again later
                    raise SkipRequest(operation_result['errors'][0].get('errorMessage'))
                else:
                    logger.error(Globals.FAIL_ACTION + operation_result['errors'][0].get('errorMessage'))
                    # Fail the Fulfilment Request if any issue encountered in the above try block
                    # Add proper validations and handle boundary and corner cases appropriately to avoid failure.
                    raise FailRequest(message=operation_result['errors'][0].get('errorMessage'))
            else:
                if "error" in operation_result:
                    logger.error("*** EXCEPTION *** {} ".format(operation_result['error']))
                    raise Exception(operation_result['error'])


    # This method processes the fulfilment request for cancelling a subscription
    @function_log
    def cancel(self, req, automation: FulfillmentAutomation):
        logger.info(f"*** Processing CANCELLATION for request {req.id} ***")

        # Check if the subscription is Active
        cancelled_subscription = self._cancel_subscription(automation, req)

        # Check if the API call was successful and save the response data in Connect
        logger.debug('Cancel Subscription response: {}'.format(Utils.serialize(cancelled_subscription)))
        # Update fulfilment parameters in Fulfilment request with the data in the response from the Vendor API call. Similar to _check_update_response

        try:
            return self.activate_template(req=req, template_type='suspendSubscriptionTemplate')
            # Returning the Activation Template will update the status of Fulfilment Request object to Approved and Subscription object status to Terminated.
            # The statuses will not get updated as Approved and Terminated if any of the mandatory/required fulfilment parameter in Fulfilment Request remain empty.

        except SkipRequest as skip:
            raise skip
        except FailRequest as err:
            logger.error(Message.Shared.ACTIVATING_TEMPLATE_ERROR.format(str(err.message)))
            # The Fulfilment Request was provisioned successfully, but Activation template could not be returned successfully.
            # Therefore, we log the error message and do not fail the request
            raise SkipRequest(Message.Shared.ACTIVATING_TEMPLATE_ERROR.format(str(err.message)))
        except Exception as ex:
            logger.error(Message.Shared.ACTIVATING_TEMPLATE_ERROR.format(str(ex)))
            raise SkipRequest(Message.Shared.ACTIVATING_TEMPLATE_ERROR.format(str(ex)))

    # This method is responsible to make the Vendor API calls to cancel a subscription
    @function_log
    def _cancel_subscription(self, automation, req):
        try:
            logger.info(f"Cancelling subscription")

            # Get the subscription Id from the request that needs to be cancelled
            subscriptionId = req.asset.get_param_by_id('subscriptionId').value

            # Prepare the body/payload for the Vendor API to cancel the subscription
            data = self._parse_cancel(req)

            # Get the Vendor API credentials.
            # Here, the Vendor API credentials are being fetched from the configuration parameter set for a Product in Connect Vendor Portal
            # The location to save Vendor API credentials can be as desired. Customize to fetch data accordingly.
            credentials = Utils.get_credentials(req.marketplace.id, req.asset.configuration, req.asset.connection.type)

            # Initiating the API client
            api_client = APIClient(credentials)

            # Send payload (data) to make the Vendor API call for cancelling subscription
            operation_result = api_client.cancel_subscription(data, subscriptionId)

            return operation_result

        except FailRequest as err:
            logger.error(Globals.FAIL_ACTION + str(err))
            raise err

    # This method is responsible to construct payload/body required to make the Vendor API call to cancel the subscription
    @function_log
    def _parse_cancel(self, req):
        logger.info("Parsing subscription {}".format(req.asset.external_id))

        # Preparing API payload/body json
        # The data needs to be as per the schema requirement of Vendor API

        # Customize and construct he JSON for cancel subscription operation as per the API schema
        data = {}
        return data


    # This method processes the fulfilment request for suspending a subscription
    @function_log
    def suspend(self, req, automation: FulfillmentAutomation):
        logger.info(f"*** Processing SUSPEND for request {req.id} ***")

        # Check if the subscription is Active

        suspended_subscription = self._suspend_subscription(automation, req)

        # Check if the API call was successful and save the response data in Connect
        logger.debug('Suspend Subscription response: {}'.format(Utils.serialize(suspended_subscription)))
        # Update fulfilment parameters in Fulfilment request with the data in the response from the Vendor API call. Similar to _check_update_response

        try:
            return self.activate_template(req=req, template_type='suspendSubscriptionTemplate')
            # Returning the Activation Template will update the status of Fulfilment Request object to Approved and Subscription object status to Suspended.
            # The statuses will not get updated as Approved and Suspended if any of the mandatory/required fulfilment parameter in Fulfilment Request remain empty.

        except SkipRequest as skip:
            raise skip
        except FailRequest as err:
            logger.error(Message.Shared.ACTIVATING_TEMPLATE_ERROR.format(str(err.message)))
            # The Fulfilment Request was provisioned successfully, but Activation template could not be returned successfully.
            # Therefore, we log the error message and do not fail the request
            raise SkipRequest(Message.Shared.ACTIVATING_TEMPLATE_ERROR.format(str(err.message)))
        except Exception as ex:
            logger.error(Message.Shared.ACTIVATING_TEMPLATE_ERROR.format(str(ex)))
            raise SkipRequest(Message.Shared.ACTIVATING_TEMPLATE_ERROR.format(str(ex)))

    # This method is responsible to make the Vendor API calls to suspend a subscription
    @function_log
    def _suspend_subscription(self, automation, req):
        try:
            logger.info(f"Suspending subscription")

            # Get the subscription Id from the request that needs to be suspended
            subscriptionId = None
            subscriptionId = req.asset.get_param_by_id('subscriptionId').value

            # Prepare the body/payload for the Vendor API to suspend the subscription
            data = self._parse_suspend(req)

            # Get the Vendor API credentials.
            # Here, the Vendor API credentials are being fetched from the configuration parameter set for a Product in Connect Vendor Portal
            # The location to save Vendor API credentials can be as desired. Customize to fetch data accordingly.
            credentials = Utils.get_credentials(req.marketplace.id, req.asset.configuration, req.asset.connection.type)

            # Initiating the API client
            api_client = APIClient(credentials)

            # Send payload (data) to make the Vendor API call for suspending subscription
            operation_result = api_client.suspend_subscription(data, subscriptionId)

            return operation_result

        except FailRequest as err:
            logger.error(Globals.FAIL_ACTION + str(err))
            raise err

    # This method is responsible to construct payload/body required to make the Vendor API call to suspend the subscription
    @function_log
    def _parse_suspend(self, req):
        logger.info("Parsing subscription {}".format(req.asset.external_id))

        # Preparing API payload/body json
        # The data needs to be as per the schema requirement of Vendor API

        # Customize and construct he JSON for cancel subscription operation as per the API schema
        data = {}
        return data


    # This method processes the fulfilment request for resuming a subscription
    @function_log
    def resume(self, req, automation: FulfillmentAutomation):
        logger.info(f"*** Processing RESUME for request {req.id} ***")

        # Check if the subscription status is Suspended

        resumed_subscription = self._resume_subscription(automation, req)

        # Check if the API call was successful and save the response data in Connect
        logger.debug('Resume Subscription response: {}'.format(Utils.serialize(resumed_subscription)))
        # Update fulfilment parameters in Fulfilment request with the data in the response from the Vendor API call. Similar to _check_update_response

        try:
            return self.activate_template(req=req, template_type='activationTemplate')
            # Returning the Activation Template will update the status of Fulfilment Request object to Approved and Subscription object status to Active.
            # The statuses will not get updated as Approved/Active if any of the mandatory/required fulfilment parameter in Fulfilment Request remain empty.

        except SkipRequest as skip:
            raise skip
        except FailRequest as err:
            logger.error(Message.Shared.ACTIVATING_TEMPLATE_ERROR.format(str(err.message)))
            # The Fulfilment Request was provisioned successfully, but Activation template could not be returned successfully.
            # Therefore, we log the error message and do not fail the request
            raise SkipRequest(Message.Shared.ACTIVATING_TEMPLATE_ERROR.format(str(err.message)))
        except Exception as ex:
            logger.error(Message.Shared.ACTIVATING_TEMPLATE_ERROR.format(str(ex)))
            raise SkipRequest(Message.Shared.ACTIVATING_TEMPLATE_ERROR.format(str(ex)))

    # This method is responsible to make the Vendor API calls to resume a subscription
    @function_log
    def _resume_subscription(self, automation, req):
        try:
            logger.info(f"Resuming subscription")

            # Get the subscription Id from the request that needs to be resumed
            subscriptionId = None
            subscriptionId = req.asset.get_param_by_id('subscriptionId').value

            # Prepare the body/payload for the Vendor API to resume the subscription
            data = self._parse_resume(req)

            # Get the Vendor API credentials.
            # Here, the Vendor API credentials are being fetched from the configuration parameter set for a Product in Connect Vendor Portal
            # The location to save Vendor API credentials can be as desired. Customize to fetch data accordingly.
            credentials = Utils.get_credentials(req.marketplace.id, req.asset.configuration, req.asset.connection.type)

            # Initiating the API client
            api_client = APIClient(credentials)

            # Send payload (data) to make the Vendor API call for resuming subscription
            operation_result = api_client.resume_subscription(data, subscriptionId)

            return operation_result

        except FailRequest as err:
            logger.error(Globals.FAIL_ACTION + str(err))
            raise err

    # This method is responsible to construct payload/body required to make the Vendor API call to resume the subscription
    @function_log
    def _parse_resume(self, req):
        logger.info("Parsing subscription {}".format(req.asset.external_id))

        # Preparing API payload/body json
        # The data needs to be as per the schema requirement of Vendor API

        # Customize and construct he JSON for resume subscription operation as per the API schema
        data = {}
        return data



    @function_log
    def activate_template(self, req, template_type):
        logger.info('Activating template')

        # Get the Activation Template by the ID saved in the configuration parameter for a marketplace
        activation_response = ActivationTemplateResponse(
            Utils.get_activation_template(configuration=req.asset.configuration, marketplace_id=req.marketplace.id,
                                          template_type=template_type))
        if len(activation_response.template_id) == 0:
            logger.error(Globals.SKIP_ACTION + Message.Shared.EMPTY_ACTIVATION_TILE.format(req.marketplace.id))
            raise SkipRequest(
                message=Message.Shared.EMPTY_ACTIVATION_TILE.format(req.marketplace.id))
        # logger.info(f'*** Finishing {action} processing of request {req.id} ***')

        return activation_response

    def check_order_parameters(self, req: Fulfillment):
        # Validate to ensure the attempt to create subscription in Vendor System does not fail.
        # For Example - If an ordering parameter is configured to provide email, check if email matches regex
        # For example - If Vendor APIs include API to validate some data before creating subscription, call it.

        params = []
        error_msg = ''
        # Regular Expression to validate any type of value. For example, email
        regex = '^[a-z0-9]+[\._]?[a-z0-9]+[@]\w+[.]\w{2,3}$'

        # Get the ordering parameter by ID
        # Ordering parameters are created in product in Connect Vendor Portal.
        email = req.asset.get_param_by_id('customer_admin_email').value

        # Check if data matches the regex
        if email:
            if (re.search(regex, email)):
                params.append(Param(id='customer_admin_email', value=email))
            else:
                error_msg = 'Please enter a valid customer admin email.'
        else:
            error_msg = 'Please enter customer admin email.'

        # If requirement is not fulfilled, change the status of the Fulfilment request of Subscription to Inquiring, as below
        if not all([
            hasattr(req.asset.get_param_by_id('customer_admin_email'), 'value')]
        ):
            raise InquireRequest(error_msg, params)
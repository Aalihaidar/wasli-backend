from django.urls import path

from . import views

urlpatterns = [
    path(
        "restaurants/<slug:slug>/conversations",
        views.OpenConversationView.as_view(),
        name="restaurants-conversations",
    ),
    path(
        "conversations/<uuid:id>/messages",
        views.ConversationMessagesView.as_view(),
        name="conversations-messages",
    ),
    path(
        "conversations/<uuid:id>/voice",
        views.ConversationVoiceView.as_view(),
        name="conversations-voice",
    ),
    path(
        "conversations/<uuid:id>/location",
        views.ConversationLocationView.as_view(),
        name="conversations-location",
    ),
]

from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from .models import ChatRoom


@login_required
def inbox(request):
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    chat_rooms = request.user.chat_rooms.all()
    chat_rooms_with_last_message = []
    all_users = request.user.get_followings_and_followers()
    current_datetime = timezone.now()

    for chat_room in chat_rooms:
        unread_notifications = chat_room.notifications.filter(
            user=request.user, is_read=False
        ).count()
        last_message = chat_room.messages.order_by("-timestamp").first()
        chat_rooms_with_last_message.append(
            (chat_room, last_message, unread_notifications)
        )

    chat_rooms_with_last_message.sort(
        key=lambda x: x[1].timestamp
        if x[1]
        else current_datetime - timedelta(days=365),
        reverse=True,
    )

    context = {
        "chat_rooms": chat_rooms_with_last_message,
        "all_users": all_users,
        "user_username": request.user.first_name,
    }

    return render(request, "chat/inbox.html", context)


@login_required
def unread_notifications(request):
    user = request.user
    chat_rooms = user.chat_rooms.all()
    chat_rooms_data = []

    for chat_room in chat_rooms:
        unread_notifications = chat_room.notifications.filter(
            user=user, is_read=False
        ).count()
        last_message = chat_room.messages.order_by("-timestamp").first()

        if last_message:
            last_message_content = last_message.content
            last_message_timestamp = last_message.formatted_timestamp()
        else:
            last_message_content = "메세지없음"
            last_message_timestamp = None

        chat_rooms_data.append(
            {
                "room_id": chat_room.pk,
                "room_name": chat_room.name,
                "unread_notifications": unread_notifications,
                "last_message": last_message_content,
                "last_message_timestamp": last_message_timestamp,
            }
        )

    response_data = {"data": chat_rooms_data}

    return JsonResponse(response_data)


@login_required
def get_new_chat_rooms(request):
    response_data = {"chat_rooms": []}
    for chat_room in request.user.chat_rooms.all():
        response_data["chat_rooms"].append({"name": chat_room.name, "pk": chat_room.pk})
    return JsonResponse(response_data)


@login_required
def start_chat(request, user_id):
    target_user = get_user_model().objects.get(id=user_id)
    chat_room = ChatRoom.get_or_create_chat_room([request.user, target_user])
    return redirect("chat:room", room_name=chat_room.name)


@login_required
def start_group_chat(request):
    if request.method == "POST":
        selected_user_ids = request.POST.getlist("user_ids")
        if selected_user_ids:
            selected_users = get_user_model().objects.filter(id__in=selected_user_ids)
            selected_users = list(selected_users) + [request.user]
            chat_room = ChatRoom.get_or_create_chat_room(selected_users)
            return redirect("chat:room", room_name=chat_room.name)
    return redirect("chat:inbox")


@login_required
def room(request, room_name):
    chat_room = ChatRoom.objects.get(name=room_name)
    messages = chat_room.messages.all()
    user = request.user
    unread_notifications = chat_room.notifications.filter(user=user, is_read=False)
    for notification in unread_notifications:
        notification.mark_as_read()

    context = {
        "room_name": room_name,
        "chat_room": chat_room,
        "messages": messages,
        "user": user,
    }
    return render(request, "chat/room.html", context)


@login_required
def delete_chat(request, room_name):
    chat_room = ChatRoom.objects.get(name=room_name)
    chat_room.delete()
    return redirect("chat:inbox")

import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import LoginView
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage, send_mail
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes, force_str, force_text
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import View

from carts.models import Cart, CartItem, Order, OrderItem
from posts.models import Post
from secondhands.models import S_Product, S_Purchase
from stores.models import Product

from .forms import (
    CustomAuthentication,
    CustomPasswordChangeForm,
    CustomUserChangeForm,
    CustomUserCreationForm,
    FindUserIDForm,
    PasswordResetRequestForm,
)
from .models import PointLog, PointLogItem


class CustomLoginView(LoginView):
    """
    login 뷰
    """

    def form_invalid(self, form):
        """
        유효성 불통과 시 호출
        """
        return JsonResponse({"status": "error", "message": "아이디, 비밀번호를 다시 확인해주세요."})

    def form_valid(self, form):
        """
        유효성 통과 시 호출
        """
        # 로그인 작업 완료
        auth_login(self.request, form.get_user())

        cart_data = self.request.POST.get("cart_data")
        if cart_data:
            cart_items = json.loads(cart_data)

            # 인증된 사용자를 사용하여 Cart 인스턴스 생성 또는 조회
            cart, created = Cart.objects.get_or_create(user=self.request.user)

            # cart_data를 CartItem에 저장, 이미 존재하는 경우 quantity 업데이트
            for item in cart_items:
                # product 인스턴스를 가져오기 (id로 조회).
                product_instance = get_object_or_404(Product, id=item["id"])

                # 기존 cart_item이 있는지 확인함
                cart_item, cart_item_created = CartItem.objects.get_or_create(
                    cart=cart, product=product_instance
                )

                if cart_item_created:
                    # 새로운 cart_item의 경우
                    cart_item.quantity = item["quantity"]
                else:
                    # 기존 cart_item의 경우 quantity를 더해줌
                    cart_item.quantity += item["quantity"]

                # 변경된 quantity 값을 저장함
                cart_item.save()

        # 로그인 한 사용자의 프로필로 리디렉션
        return JsonResponse(
            {"status": "success", "redirect_url": self.get_success_url()}
        )


"""
# 현재 비사용중

def login(request):

    print("login 사용 - 2번")
    if request.user.is_authenticated:
        return redirect("main")

    if request.method == "POST":
        form = CustomAuthentication(request, request.POST)
        if form.is_valid():
            user = form.get_user()
            if not user.is_active:
                User = get_user_model()
                inactive_user = User.objects.filter(
                    username=user.username, is_active=False
                ).first()
                if inactive_user:
                    messages.warning(
                        request,
                        "이전에 가입한 미활성화 된 계정이 있습니다. 계정을 재등록하려면 사용자 이름과 이메일을 사용해 회원 가입을 다시 시도하십시오.",
                    )
                    return redirect(reverse("accounts:signup"))
                else:
                    messages.error(request, "이메일 확인이 필요합니다.")
                    return HttpResponseRedirect(reverse("accounts:login"))
            else:
                auth_login(request, user)
                return redirect("main")
    else:
        form = CustomAuthentication()

    context = {
        "form": form,
    }

    return render(request, "accounts/login.html", context)
"""


@login_required
def logout(request):
    """
    logout 함수
    """
    if request.user.is_authenticated:
        auth_logout(request)
    return redirect("main")


class SignupView(View):
    """
    signup 뷰
    """
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("main")

        form = CustomUserCreationForm()
        context = {
            "form": form,
        }
        return render(request, "accounts/signup.html", context)

    def post(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("main")

        form = CustomUserCreationForm(request.POST, request.FILES)

        if form.is_valid():
            inactive_user = User.objects.filter(
                username=form.cleaned_data.get("username"),
                email=form.cleaned_data.get("email"),
                is_active=False,
            ).first()
            is_seller = request.POST.get("is_seller")

            if inactive_user:
                try:
                    with transaction.atomic():
                        inactive_user.set_password(form.cleaned_data.get("password1"))
                        inactive_user.address = request.POST.get("address")
                        inactive_user.full_clean()
                        inactive_user.save()

                    domain = request.get_host()
                    mail_subject = "재활성화 이메일 인증"
                    message = render_to_string(
                        "accounts/reactivate_email.html",
                        {
                            "user": inactive_user,
                            "domain": domain,
                            "uidb64": urlsafe_base64_encode(
                                force_bytes(inactive_user.pk)
                            ),
                            "token": default_token_generator.make_token(inactive_user),
                        },
                    )

                    to_email = form.cleaned_data.get("email")
                    email = EmailMessage(mail_subject, message, to=[to_email])
                    email.send()

                    return render(request, "accounts/wait_for_email.html")

                except ValidationError as ex:
                    messages.error(request, str(ex))
                    return redirect(reverse("accounts:signup"))

            user = form.save(commit=False)
            user.address = request.POST.get("address")
            user.is_seller = is_seller
            user.is_active = False  # Deactivate user until email confirmation
            user.save()

            # Send email activation message
            domain = request.get_host()
            mail_subject = "계정 활성화"
            message = render_to_string(
                "accounts/activate_email.html",
                {
                    "user": user,
                    "domain": domain,
                    "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
                    "token": default_token_generator.make_token(user),
                },
            )

            # Send email
            to_email = form.cleaned_data.get("email")
            email = EmailMessage(mail_subject, message, to=[to_email])
            email.send()
            return JsonResponse({"status": "success"})

        context = {
            "form": form,
        }
        return render(request, "accounts/signup.html", context)


def activate(request, uidb64, token):
    """
    사용자 계정 활성화 요청 처리하는 함수
    """
    User = get_user_model()
    try:
        uid = force_text(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        messages.success(request, "가입이 성공적으로 완료되었습니다!")
        return redirect("accounts:login")
    else:
        messages.error(request, "이메일 인증 링크가 잘못되었습니다.")
        return HttpResponse("활성화 링크가 유효하지 않습니다.")


def user_is_authenticated(user):
    return user.is_authenticated and user.is_active


@user_passes_test(user_is_authenticated, login_url="/accounts/login/")
def main(request):
    return render(request, "main.html")


@login_required
def delete(request):
    request.user.delete()
    auth_logout(request)
    return redirect("main")


@login_required
def update(request):
    """
    개인정보 수정 함수
    """
    if request.method == "POST":
        form = CustomUserChangeForm(
            request.POST, files=request.FILES, instance=request.user
        )
        if form.is_valid():
            user = form.save(commit=False)
            user.address = request.POST.get("address")
            form.save()
            return redirect("main")
    else:
        form = CustomUserChangeForm(instance=request.user)

    context = {"form": form}
    return render(request, "accounts/update.html", context)


@login_required
def change_password(request):
    """
    비밀번호 변경 함수
    """
    if request.method == "POST":
        form = CustomPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            return redirect("main")
    else:
        form = CustomPasswordChangeForm(request.user)

    context = {
        "form": form,
    }
    return render(request, "accounts/change_password.html", context)


User = get_user_model()


def find_user_id(request):
    """
    아이디 찾기 함수
    """
    if request.method == "POST":
        form = FindUserIDForm(request.POST)
        if form.is_valid():
            last_name = form.cleaned_data["last_name"]
            email = form.cleaned_data["email"]
            users = User.objects.filter(email=email)
            if users:
                for user in users:
                    messages.success(
                        request,
                        f"찾으신 이름: {user.last_name} <br><br> 이메일: {user.email} <br><br> 사용자명: {user.username}",
                    )
                return redirect("accounts:find_user_id")
            else:
                messages.error(request, "입력하신 이메일로 가입된 아이디를 찾을 수 없습니다.")
                return redirect("accounts:find_user_id")
    else:
        form = FindUserIDForm()
    return render(request, "accounts/find_user_id.html", {"form": form})


def password_reset_request(request):
    """
    비밀번호 재설정 함수
    """
    if request.method == "POST":
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            user = User.objects.filter(email=email).first()
            if user:
                # 이메일 발송 로직
                subject = "비밀번호 재설정 요청"
                email_template_name = "accounts/password_reset_email.html"
                uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                default_path = reverse(
                    "accounts:password_reset_confirm",
                    kwargs={"uidb64": uidb64, "token": token},
                )
                c = {
                    "email": user.email,
                    "domain": request.META["HTTP_HOST"],
                    "site_name": "your_site_name",
                    "uid": uidb64,
                    "user": user,
                    "token": token,
                    "protocol": "https",
                    "path": default_path,
                }
                email = render_to_string(email_template_name, c)
                send_mail(
                    subject,
                    email,
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=False,
                )
                messages.success(request, "비밀번호 재설정 이메일이 발송되었습니다.")
                return redirect("accounts:password_reset_request")
            else:
                messages.error(request, "입력한 사용자명에 해당하는 계정을 찾을 수 없습니다.")
                return redirect("accounts:password_reset_request")
    else:
        form = PasswordResetRequestForm()
    return render(request, "accounts/password_reset_request.html", {"form": form})


def password_reset_confirm(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    # 기본 토큰 생성기를 사용한 토큰 검사
    if user is not None and default_token_generator.check_token(user, token):
        form = SetPasswordForm(user, request.POST or None)
        form.fields["new_password1"].widget.attrs["placeholder"] = "새 비밀번호"
        form.fields["new_password2"].widget.attrs["placeholder"] = "새 비밀번호 확인"
        if request.method == "POST":
            if form.is_valid():
                form.save()
                messages.success(request, "비밀번호가 변경되었습니다.")
                return redirect("accounts:login")
        return render(request, "accounts/password_reset_confirm.html", {"form": form})
    else:
        messages.error(request, "비밀번호 재설정 링크가 유효하지 않습니다.")
        return redirect("accounts:password_reset_request")


@login_required
def profile(request, username):
    q = request.GET.get("q")
    User = get_user_model()
    person = User.objects.get(username=username)
    posts = Post.objects.filter(user=person)
    interests = request.user.like_products.all()
    orders = (
        Order.objects.filter(customer=person)
        .exclude(shipping_status="결제전")
        .order_by("-pk")
    )
    sells = Order.objects.filter(seller=person, shipping_status="배송준비중").order_by("-pk")
    purchases = S_Purchase.objects.filter(customer=person).select_related("product")
    completed_products = S_Product.objects.filter(user=person, status="3")
    purchase_details = []

    for order in orders:
        items = OrderItem.objects.filter(order=order)
        purchase_details.append({"order": order, "items": items})

    selled_products = []
    for sell in sells:
        items = OrderItem.objects.filter(order=sell)
        selled_products.append({"sell": sell, "items": items})

    point_log, _ = PointLog.objects.get_or_create(user=person)
    point_log_items = point_log.point_log_itmes.all().order_by("-pk")[:5]
    context = {
        "q": q,
        "person": person,
        "posts": posts,
        "interests": interests,
        "purchase_details": purchase_details,
        "completed_products": completed_products,
        "selled_products": selled_products,
        "point_log_items": point_log_items,
        # 'purchases': purchases,
    }
    return render(request, "accounts/profile.html", context)


@login_required
def follow(request, user_pk):
    User = get_user_model()
    person = User.objects.get(pk=user_pk)

    if person != request.user:
        if request.user in person.followers.all():
            person.followers.remove(request.user)
            is_followed = False
        else:
            person.followers.add(request.user)
            is_followed = True
        context = {
            "is_followed": is_followed,
            "followings_count": person.followings.count(),
            "followers_count": person.followers.count(),
        }
        return JsonResponse(context)
    return redirect("accounts:profile", person.username)


@login_required
def following_list(request, username):
    User = get_user_model()
    person = User.objects.get(username=username)
    followings = person.followings.all()
    context = {
        "followings": followings,
    }
    return render(request, "accounts/following_list.html", context)


@login_required
def followers_list(request, username):
    User = get_user_model()
    person = User.objects.get(username=username)
    followers = person.followers.all()
    context = {
        "followers": followers,
    }
    return render(request, "accounts/followers_list.html", context)


@csrf_exempt
def check_username(request):
    username = request.POST.get("username")
    if User.objects.filter(username=username).exists():
        return JsonResponse({"is_available": False})
    return JsonResponse({"is_available": True})


@csrf_exempt
def check_first_name(request):
    first_name = request.POST.get("first_name")
    if User.objects.filter(first_name=first_name).exists():
        return JsonResponse({"is_available": False})
    return JsonResponse({"is_available": True})


@csrf_exempt
def check_email(request):
    email = request.POST.get("email")
    if User.objects.filter(email=email).exists():
        return JsonResponse({"is_available": False})
    return JsonResponse({"is_available": True})

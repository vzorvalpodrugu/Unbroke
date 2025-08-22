from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import CreateView
from django.contrib import messages

from .forms import CustomUserCreationForm, CustomAuthenticationForm


class UserRegisterView(CreateView):
    template_name = "user_templates/register.html"
    form_class = CustomUserCreationForm
    success_url = reverse_lazy("landing")

    def form_valid(self, form):
        messages.success(self.request, "Registration successful! 🎉")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request,
                       "Registration failed. Please check the form.")
        return super().form_invalid(form)


class UserLoginView(LoginView):
    template_name = "user_templates/login.html"
    authentication_form = CustomAuthenticationForm

    def get_success_url(self):
        return reverse_lazy("landing")

    def form_valid(self, form):
        messages.success(self.request, "Login successful! 🚀")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request,
                       "Login failed. Please check your credentials.")
        return super().form_invalid(form)


class UserLogoutView(LogoutView):
    next_page = reverse_lazy("landing")
